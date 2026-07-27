"""Tests für app/services/security.py (Keys, Tokens, Verschlüsselung, Admin-Check)"""
import hashlib
import os
import stat
import time

import pytest

from app.services import jobs_store as jobs_store_module
from app.services import security
from app.services.jobs_store import initialize_jobs_store
from app.services.security import (
    SecretDecryptionError,
    admin_password_configured,
    create_token,
    decrypt_secret,
    encrypt_secret,
    get_admin_user,
    get_master_key,
    get_token_expiry,
    hash_password,
    reset_key_cache,
    setup_required,
    verify_admin,
    verify_password,
    verify_token,
)


@pytest.fixture(autouse=True)
def _fixed_secret_key(monkeypatch):
    """Deterministischer Key pro Test + Cache-Reset"""
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    reset_key_cache()
    yield
    reset_key_cache()


class TestMasterKey:
    def test_env_key_is_32_bytes(self):
        assert len(get_master_key()) == 32

    def test_env_key_deterministic(self):
        key1 = get_master_key()
        reset_key_cache()
        key2 = get_master_key()
        assert key1 == key2

    def test_keyfile_autogen(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SSA_SECRET_KEY", raising=False)
        reset_key_cache()
        key_file = tmp_path / "secret.key"
        monkeypatch.setattr(security, "_secret_key_file", lambda: key_file)

        key = get_master_key()
        assert key_file.exists()
        assert len(key) == 32
        # Datei-Berechtigungen: nur Owner
        mode = stat.S_IMODE(key_file.stat().st_mode)
        assert mode == 0o600

        # Zweiter Aufruf nach Cache-Reset liest dieselbe Datei
        reset_key_cache()
        assert get_master_key() == key


class TestToken:
    def test_roundtrip(self):
        token = create_token("admin")
        assert verify_token(token) == "admin"

    def test_expiry_in_future(self):
        token = create_token("admin", ttl_hours=1)
        expiry = get_token_expiry(token)
        assert expiry is not None
        assert expiry > time.time()

    def test_expired_token_rejected(self):
        token = create_token("admin", ttl_hours=1)
        # Payload mit abgelaufener Zeit nachbauen: einfacher Trick über ttl=0 geht
        # nicht (min 1), daher manipulierte Expiry prüfen wir über verify direkt:
        import base64, hashlib, hmac, json

        payload = json.dumps(
            {"u": "admin", "exp": int(time.time()) - 10}, separators=(",", ":")
        ).encode()
        sig = hmac.new(security._token_key(), payload, hashlib.sha256).digest()
        expired = (
            base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
            + "."
            + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
        )
        assert verify_token(expired) is None
        assert verify_token(token) == "admin"

    def test_tampered_signature_rejected(self):
        token = create_token("admin")
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        assert verify_token(tampered) is None

    def test_tampered_payload_rejected(self):
        token = create_token("admin")
        payload_b64, sig_b64 = token.split(".", 1)
        other = create_token("someone-else").split(".", 1)[0]
        assert verify_token(f"{other}.{sig_b64}") is None or other == payload_b64

    def test_garbage_rejected(self):
        assert verify_token("") is None
        assert verify_token("kein-token") is None
        assert verify_token("a.b.c") is None

    def test_key_rotation_invalidates(self, monkeypatch):
        token = create_token("admin")
        monkeypatch.setenv("SSA_SECRET_KEY", "anderer-key")
        reset_key_cache()
        assert verify_token(token) is None


class TestSecretEncryption:
    def test_roundtrip(self):
        assert decrypt_secret(encrypt_secret("geheimes-passwort")) == "geheimes-passwort"

    def test_ciphertext_differs_from_plaintext(self):
        assert encrypt_secret("pw") != "pw"

    def test_wrong_key_raises(self, monkeypatch):
        ciphertext = encrypt_secret("pw")
        monkeypatch.setenv("SSA_SECRET_KEY", "rotierter-key")
        reset_key_cache()
        with pytest.raises(SecretDecryptionError):
            decrypt_secret(ciphertext)


class TestVerifyAdmin:
    def test_correct_credentials(self, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "pw123")
        assert verify_admin("admin", "pw123") is True

    def test_wrong_password(self, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "pw123")
        assert verify_admin("admin", "falsch") is False

    def test_wrong_username(self, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "pw123")
        assert verify_admin("root", "pw123") is False

    def test_custom_username(self, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "pw123")
        monkeypatch.setenv("SSA_ADMIN_USER", "benjamin")
        assert verify_admin("benjamin", "pw123") is True
        assert verify_admin("admin", "pw123") is False

    def test_fail_closed_without_password(self, monkeypatch):
        monkeypatch.delenv("SSA_ADMIN_PASSWORD", raising=False)
        assert verify_admin("admin", "") is False
        assert verify_admin("admin", "irgendwas") is False

    def test_empty_env_password_counts_as_unset(self, monkeypatch):
        # docker compose setzt bei ${SSA_ADMIN_PASSWORD:-} den leeren String
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "")
        assert admin_password_configured() is False
        assert verify_admin("admin", "") is False


class TestPasswordHashing:
    def test_roundtrip(self):
        stored = hash_password("geheim123")
        assert stored.startswith("scrypt$")
        assert verify_password("geheim123", stored) is True

    def test_salt_makes_hashes_differ(self):
        assert hash_password("geheim123") != hash_password("geheim123")

    def test_wrong_password(self):
        assert verify_password("falsch", hash_password("geheim123")) is False

    @pytest.mark.parametrize(
        "stored",
        [
            "",
            "muell",
            "unbekannt$1$aaaa$bbbb",
            "scrypt$16384$8",  # zu wenige Felder
            "scrypt$nichtnumerisch$8$1$aaaa$bbbb",
            "pbkdf2_sha256$600000",
        ],
    )
    def test_broken_hash_is_fail_closed(self, stored):
        assert verify_password("geheim123", stored) is False

    def test_empty_password_never_verifies(self):
        assert verify_password("", hash_password("geheim123")) is False

    def test_pbkdf2_format_verifies(self):
        # Von Hand gebaut - so sehen Hashes aus, die auf einem Build ohne
        # scrypt entstanden sind.
        salt = b"0123456789abcdef"
        rounds = 1000
        dk = hashlib.pbkdf2_hmac("sha256", b"geheim123", salt, rounds, dklen=32)
        stored = (
            f"pbkdf2_sha256${rounds}"
            f"${security._b64url_encode(salt)}${security._b64url_encode(dk)}"
        )
        assert verify_password("geheim123", stored) is True
        assert verify_password("falsch", stored) is False

    def test_falls_back_to_pbkdf2_without_scrypt(self, monkeypatch):
        def no_scrypt(*args, **kwargs):
            raise ValueError("scrypt nicht verfügbar")

        monkeypatch.setattr(security.hashlib, "scrypt", no_scrypt)
        stored = hash_password("geheim123")
        assert stored.startswith("pbkdf2_sha256$")
        # Die Verifikation läuft ebenfalls ohne scrypt
        assert verify_password("geheim123", stored) is True


class TestStoredAdminCredentials:
    """Admin-Konto aus der Ersteinrichtung (Datenbank statt Umgebung)"""

    @pytest.fixture
    def store(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SSA_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("SSA_ADMIN_USER", raising=False)
        return initialize_jobs_store(tmp_path / "jobs.db")

    def test_login_against_database(self, store):
        assert store.create_admin_credentials("benjamin", hash_password("geheim123"))
        assert admin_password_configured() is True
        assert setup_required() is False
        assert get_admin_user() == "benjamin"
        assert verify_admin("benjamin", "geheim123") is True
        assert verify_admin("benjamin", "falsch") is False
        assert verify_admin("admin", "geheim123") is False

    def test_env_wins_over_database(self, store, monkeypatch):
        store.create_admin_credentials("benjamin", hash_password("db-passwort"))
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "env-passwort")

        assert get_admin_user() == "admin"
        assert verify_admin("admin", "env-passwort") is True
        # Das in der Datenbank gespeicherte Konto ist währenddessen wirkungslos
        assert verify_admin("benjamin", "db-passwort") is False

    def test_setup_required_on_fresh_database(self, store):
        assert setup_required() is True
        assert verify_admin("admin", "irgendwas") is False

    def test_unreadable_store_is_fail_closed(self, monkeypatch):
        monkeypatch.delenv("SSA_ADMIN_PASSWORD", raising=False)

        def boom():
            raise RuntimeError("Datenbank weg")

        monkeypatch.setattr(jobs_store_module, "get_jobs_store", boom)
        assert security._stored_admin() is None
        assert verify_admin("admin", "irgendwas") is False
