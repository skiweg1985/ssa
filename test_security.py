"""Tests für app/services/security.py (Keys, Tokens, Verschlüsselung, Admin-Check)"""
import os
import stat
import time

import pytest

from app.services import security
from app.services.security import (
    SecretDecryptionError,
    create_token,
    decrypt_secret,
    encrypt_secret,
    get_master_key,
    get_token_expiry,
    reset_key_cache,
    verify_admin,
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
