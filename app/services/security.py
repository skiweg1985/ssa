"""Sicherheits-Service: Master-Key, Auth-Tokens und Verschlüsselung von Secrets.

Key-Quellen (in dieser Reihenfolge):
1. Umgebungsvariable SSA_SECRET_KEY (beliebiger String, wird per SHA-256 auf 32 Bytes gebracht)
2. Auto-generierte Datei data/secret.key (32 Zufallsbytes, chmod 600, überlebt Neustarts)

Aus dem Master-Key werden per HMAC zwei Subkeys abgeleitet:
- Token-Signing-Key (HMAC-signierte, zustandslose Auth-Tokens)
- Fernet-Key (Verschlüsselung der NAS-Passwörter at rest)
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Standard-TTL für Auth-Tokens: 7 Tage
DEFAULT_TOKEN_TTL_HOURS = 168

_master_key: Optional[bytes] = None


def _secret_key_file() -> Path:
    """Pfad zur auto-generierten Key-Datei (im data/-Verzeichnis, gitignored)"""
    return Path(__file__).parent.parent.parent / "data" / "secret.key"


def get_master_key() -> bytes:
    """
    Liefert den 32-Byte-Master-Key.

    Bevorzugt SSA_SECRET_KEY aus der Umgebung; sonst wird einmalig eine
    Key-Datei unter data/secret.key erzeugt und fortan wiederverwendet.
    """
    global _master_key
    if _master_key is not None:
        return _master_key

    env_key = os.environ.get("SSA_SECRET_KEY")
    if env_key:
        _master_key = hashlib.sha256(env_key.encode("utf-8")).digest()
        return _master_key

    key_file = _secret_key_file()
    if key_file.exists():
        data = key_file.read_bytes()
        if len(data) >= 32:
            _master_key = data[:32]
            return _master_key
        logger.warning(f"Ungültige Key-Datei {key_file} (zu kurz) - wird neu erzeugt")

    key_file.parent.mkdir(parents=True, exist_ok=True)
    new_key = secrets.token_bytes(32)
    key_file.write_bytes(new_key)
    try:
        os.chmod(key_file, 0o600)
    except OSError:  # z.B. auf Windows nicht unterstützt
        pass
    logger.info(f"Neuer Secret-Key erzeugt: {key_file}")
    _master_key = new_key
    return _master_key


def reset_key_cache() -> None:
    """Setzt den Key-Cache zurück (für Tests)"""
    global _master_key
    _master_key = None


def _token_key() -> bytes:
    return hmac.new(get_master_key(), b"token-signing", hashlib.sha256).digest()


def _fernet() -> Fernet:
    raw = hmac.new(get_master_key(), b"fernet-encryption", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(raw[:32]))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def get_token_ttl_hours() -> int:
    """Token-Lebensdauer in Stunden (SSA_TOKEN_TTL_HOURS, Default 168 = 7 Tage)"""
    try:
        return max(1, int(os.environ.get("SSA_TOKEN_TTL_HOURS", DEFAULT_TOKEN_TTL_HOURS)))
    except (TypeError, ValueError):
        return DEFAULT_TOKEN_TTL_HOURS


def create_token(username: str, ttl_hours: Optional[int] = None) -> str:
    """
    Erzeugt ein zustandsloses, HMAC-signiertes Auth-Token.

    Format: b64url(json{u, exp}) + "." + b64url(hmac_sha256(payload))
    """
    if ttl_hours is None:
        ttl_hours = get_token_ttl_hours()
    payload = json.dumps(
        {"u": username, "exp": int(time.time()) + ttl_hours * 3600},
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_token_key(), payload, hashlib.sha256).digest()
    return f"{_b64url_encode(payload)}.{_b64url_encode(signature)}"


def get_token_expiry(token: str) -> Optional[int]:
    """Liefert den exp-Unix-Timestamp eines (gültigen) Tokens, sonst None"""
    if verify_token(token) is None:
        return None
    try:
        payload = json.loads(_b64url_decode(token.split(".")[0]))
        return int(payload["exp"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def verify_token(token: str) -> Optional[str]:
    """
    Prüft ein Auth-Token. Liefert den Benutzernamen bei Gültigkeit, sonst None.
    """
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _b64url_decode(payload_b64)
        signature = _b64url_decode(signature_b64)
    except (ValueError, TypeError):
        return None

    expected = hmac.new(_token_key(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        data = json.loads(payload)
        if int(data["exp"]) < time.time():
            return None
        username = data["u"]
        if not isinstance(username, str) or not username:
            return None
        return username
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def encrypt_secret(plaintext: str) -> str:
    """Verschlüsselt ein Secret (z.B. NAS-Passwort) für die Speicherung"""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


class SecretDecryptionError(Exception):
    """Gespeichertes Secret kann nicht entschlüsselt werden (z.B. Key rotiert)"""


def decrypt_secret(ciphertext: str) -> str:
    """
    Entschlüsselt ein gespeichertes Secret.

    Raises:
        SecretDecryptionError: wenn der Key nicht (mehr) passt
    """
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as e:
        raise SecretDecryptionError(
            "Gespeichertes Passwort kann nicht entschlüsselt werden - "
            "bitte neu eingeben (Secret-Key wurde möglicherweise geändert)"
        ) from e


def generate_api_token() -> str:
    """Erzeugt ein neues statisches API-Token (für Monitoring-Systeme)"""
    return f"ssa_{secrets.token_urlsafe(32)}"


def hash_api_token(token: str) -> str:
    """Hash eines API-Tokens für die Speicherung (Klartext wird nie gespeichert)"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_admin_user() -> str:
    """Konfigurierter Admin-Benutzername (SSA_ADMIN_USER, Default 'admin')"""
    return os.environ.get("SSA_ADMIN_USER", "admin")


def admin_password_configured() -> bool:
    """True, wenn SSA_ADMIN_PASSWORD gesetzt (und nicht leer) ist"""
    return bool(os.environ.get("SSA_ADMIN_PASSWORD"))


def verify_admin(username: str, password: str) -> bool:
    """
    Prüft Benutzername + Passwort gegen die Umgebung.

    Fail-closed: Ohne gesetztes SSA_ADMIN_PASSWORD schlägt der Login immer fehl.
    """
    expected_password = os.environ.get("SSA_ADMIN_PASSWORD")
    if not expected_password:
        return False
    user_ok = secrets.compare_digest(
        username.encode("utf-8"), get_admin_user().encode("utf-8")
    )
    pass_ok = secrets.compare_digest(
        password.encode("utf-8"), expected_password.encode("utf-8")
    )
    return user_ok and pass_ok
