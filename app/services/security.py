"""Sicherheits-Service: Master-Key, Auth-Tokens und Verschlüsselung von Secrets.

Key-Quellen (in dieser Reihenfolge):
1. Umgebungsvariable SSA_SECRET_KEY (beliebiger String, wird per SHA-256 auf 32 Bytes gebracht)
2. Auto-generierte Datei data/secret.key (32 Zufallsbytes, chmod 600, überlebt Neustarts)

Aus dem Master-Key werden per HMAC zwei Subkeys abgeleitet:
- Token-Signing-Key (HMAC-signierte, zustandslose Auth-Tokens)
- Fernet-Key (Verschlüsselung der NAS-Passwörter at rest)

Admin-Zugangsdaten kommen aus zwei Quellen, die nie gemischt werden:
1. SSA_ADMIN_PASSWORD + SSA_ADMIN_USER aus der Umgebung (Vorrang, Klartextvergleich)
2. Ersteinrichtung über die Weboberfläche - Benutzername und scrypt-Hash in app_meta

Der Hash hängt nicht am Master-Key: eine Key-Rotation macht das Admin-Konto nicht
unbrauchbar (anders als die verschlüsselten NAS-Passwörter).
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
from typing import Dict, Optional

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


# --- Passwort-Hashing (Admin-Konto aus der Ersteinrichtung) ------------------
#
# scrypt ist speicherhart und damit gegen GPU-Bruteforce deutlich besser als
# PBKDF2. Es haengt aber an OpenSSL - fehlt es in einem exotischen Build, ist
# PBKDF2 immer noch weit besser als gar nichts. Der Algorithmus-Prefix im
# Speicherformat sorgt dafuer, dass beide Varianten nebeneinander existieren
# und Parameter spaeter aenderbar sind, ohne alte Hashes zu entwerten:
#
#   scrypt$<n>$<r>$<p>$<b64url(salt)>$<b64url(dk)>
#   pbkdf2_sha256$<rounds>$<b64url(salt)>$<b64url(dk)>
ADMIN_HASH_SCRYPT_N = 2 ** 14
ADMIN_HASH_SCRYPT_R = 8
ADMIN_HASH_SCRYPT_P = 1
ADMIN_HASH_PBKDF2_ROUNDS = 600_000
# Ohne explizites maxmem greift OpenSSLs 32-MB-Grenze - wer n erhoeht, laeuft
# sonst ohne Vorwarnung in einen ValueError.
ADMIN_HASH_MAXMEM = 64 * 1024 * 1024
ADMIN_HASH_SALT_BYTES = 16
ADMIN_HASH_KEY_BYTES = 32


def hash_password(password: str) -> str:
    """Hasht ein Passwort für die Speicherung (scrypt, Fallback PBKDF2-HMAC-SHA256)"""
    salt = secrets.token_bytes(ADMIN_HASH_SALT_BYTES)
    try:
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=ADMIN_HASH_SCRYPT_N,
            r=ADMIN_HASH_SCRYPT_R,
            p=ADMIN_HASH_SCRYPT_P,
            dklen=ADMIN_HASH_KEY_BYTES,
            maxmem=ADMIN_HASH_MAXMEM,
        )
    except (AttributeError, ValueError) as e:
        logger.warning(f"scrypt nicht verfügbar ({e}) - nutze PBKDF2-HMAC-SHA256")
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            ADMIN_HASH_PBKDF2_ROUNDS,
            dklen=ADMIN_HASH_KEY_BYTES,
        )
        return (
            f"pbkdf2_sha256${ADMIN_HASH_PBKDF2_ROUNDS}"
            f"${_b64url_encode(salt)}${_b64url_encode(dk)}"
        )
    return (
        f"scrypt${ADMIN_HASH_SCRYPT_N}${ADMIN_HASH_SCRYPT_R}${ADMIN_HASH_SCRYPT_P}"
        f"${_b64url_encode(salt)}${_b64url_encode(dk)}"
    )


def verify_password(password: str, stored: str) -> bool:
    """
    Prüft ein Passwort gegen einen gespeicherten Hash (konstantzeitig).

    Fail-closed: leerer, unbekannter oder beschädigter Hash ergibt immer False.
    """
    if not stored or not password:
        return False

    parts = stored.split("$")
    try:
        if parts[0] == "scrypt":
            n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
            salt, expected = _b64url_decode(parts[4]), _b64url_decode(parts[5])
            candidate = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=n,
                r=r,
                p=p,
                dklen=len(expected),
                maxmem=ADMIN_HASH_MAXMEM,
            )
        elif parts[0] == "pbkdf2_sha256":
            rounds = int(parts[1])
            salt, expected = _b64url_decode(parts[2]), _b64url_decode(parts[3])
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, rounds, dklen=len(expected)
            )
        else:
            return False
    except (AttributeError, ValueError, IndexError, TypeError) as e:
        logger.warning(f"Gespeicherter Passwort-Hash ist unbrauchbar: {e}")
        return False

    return hmac.compare_digest(candidate, expected)


def _stored_admin() -> Optional[Dict[str, str]]:
    """
    Admin-Zugangsdaten aus der Datenbank (Ersteinrichtung), oder None.

    Der Import passiert bewusst lazy: jobs_store importiert dieses Modul auf
    Modulebene (encrypt_secret/decrypt_secret), der Rückweg wäre ein Zyklus.
    Gleiches Muster wie in app/api/deps.py.

    Fehlertolerant: Ist der Store noch nicht initialisiert oder die DB nicht
    lesbar, gilt "nicht konfiguriert" - fail-closed statt Absturz im Login.
    """
    try:
        from app.services.jobs_store import jobs_store

        return jobs_store.get_admin_credentials()
    except Exception as e:
        logger.debug(f"Admin-Zugangsdaten aus der Datenbank nicht lesbar: {e}")
        return None


def get_admin_user() -> str:
    """
    Konfigurierter Admin-Benutzername.

    Ist SSA_ADMIN_PASSWORD gesetzt, gilt SSA_ADMIN_USER (Default 'admin') -
    Umgebung und Datenbank werden nie gemischt. Sonst der bei der
    Ersteinrichtung gespeicherte Name.
    """
    if os.environ.get("SSA_ADMIN_PASSWORD"):
        return os.environ.get("SSA_ADMIN_USER", "admin")
    stored = _stored_admin()
    if stored:
        return stored["username"]
    return os.environ.get("SSA_ADMIN_USER", "admin")


def admin_password_configured() -> bool:
    """True, wenn ein Admin-Passwort existiert - aus der Umgebung ODER der Datenbank"""
    if os.environ.get("SSA_ADMIN_PASSWORD"):
        return True
    return _stored_admin() is not None


def setup_required() -> bool:
    """True, solange noch kein Admin-Konto existiert (Ersteinrichtung offen)"""
    return not admin_password_configured()


def verify_admin(username: str, password: str) -> bool:
    """
    Prüft Benutzername + Passwort.

    Quelle 1 (Vorrang): SSA_ADMIN_PASSWORD aus der Umgebung, Klartextvergleich.
    Quelle 2: gehashtes Passwort aus der Datenbank (Web-Ersteinrichtung).

    Fail-closed: Ohne beides schlägt der Login immer fehl.
    """
    env_password = os.environ.get("SSA_ADMIN_PASSWORD")
    if env_password:
        user_ok = secrets.compare_digest(
            username.encode("utf-8"),
            os.environ.get("SSA_ADMIN_USER", "admin").encode("utf-8"),
        )
        pass_ok = secrets.compare_digest(
            password.encode("utf-8"), env_password.encode("utf-8")
        )
        return user_ok and pass_ok

    stored = _stored_admin()
    if stored is None:
        return False
    # Der Hash wird immer geprüft, auch bei falschem Benutzernamen - sonst
    # verriete die Antwortzeit, ob der Name stimmt.
    pass_ok = verify_password(password, stored["password_hash"])
    user_ok = secrets.compare_digest(
        username.encode("utf-8"), stored["username"].encode("utf-8")
    )
    return user_ok and pass_ok
