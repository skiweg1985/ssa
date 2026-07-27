"""Tests für die Ersteinrichtung über die Weboberfläche.

Deckt das ab, was der Wizard verspricht: ohne jede Konfiguration startklar,
danach genau ein Admin-Konto - und keine zweite Chance, es zu übernehmen.
"""
import pytest
from fastapi.testclient import TestClient

from app.services.jobs_store import (
    ADMIN_PASSWORD_HASH_KEY,
    initialize_jobs_store,
    jobs_store,
)
from app.services.rate_limit import login_rate_limiter
from app.services.security import reset_key_cache


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Frischer Server ohne jede Admin-Konfiguration"""
    # Der Import zuerst: app.main ruft beim Laden load_dotenv() auf und würde
    # eine .env des Entwicklers nachträglich wieder in die Umgebung schreiben.
    from app.main import app

    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    monkeypatch.delenv("SSA_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SSA_ADMIN_USER", raising=False)
    monkeypatch.delenv("SSA_SETUP_TOKEN", raising=False)
    reset_key_cache()
    login_rate_limiter.reset()

    import app.services.storage as storage_module

    test_storage = storage_module.ScanStorage(db_path=tmp_path / "test.db")
    monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
    initialize_jobs_store(tmp_path / "test.db")

    with TestClient(app) as test_client:
        yield test_client

    login_rate_limiter.reset()
    reset_key_cache()


def _setup(client, username="benjamin", password="geheim123", **extra):
    return client.post(
        "/api/auth/setup",
        json={"username": username, "password": password, **extra},
    )


class TestSetupStatus:
    def test_required_on_fresh_install(self, client):
        body = client.get("/api/auth/setup-status").json()
        assert body == {
            "setup_required": True,
            "username": "admin",
            "token_required": False,
        }

    def test_not_required_with_env_password(self, client, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "aus-der-umgebung")
        body = client.get("/api/auth/setup-status").json()
        assert body["setup_required"] is False

    def test_suggests_configured_username(self, client, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_USER", "benjamin")
        assert client.get("/api/auth/setup-status").json()["username"] == "benjamin"

    def test_needs_no_token(self, client):
        # Der Status muss vor dem Login erreichbar sein - sonst gäbe es keinen
        # Weg, den Setup-Bildschirm überhaupt anzuzeigen.
        assert client.get("/api/auth/setup-status").status_code == 200


class TestSetup:
    def test_creates_account_and_logs_in(self, client):
        response = _setup(client)
        assert response.status_code == 200

        body = response.json()
        assert body["username"] == "benjamin"
        assert body["expires_at"]

        headers = {"Authorization": f"Bearer {body['token']}"}
        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["username"] == "benjamin"

        assert client.get("/api/auth/setup-status").json()["setup_required"] is False

    def test_login_works_afterwards(self, client):
        _setup(client)

        ok = client.post(
            "/api/auth/login", json={"username": "benjamin", "password": "geheim123"}
        )
        assert ok.status_code == 200

        assert (
            client.post(
                "/api/auth/login",
                json={"username": "benjamin", "password": "falsch"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "geheim123"},
            ).status_code
            == 401
        )

    def test_second_setup_is_rejected(self, client):
        assert _setup(client).status_code == 200

        response = _setup(client, username="angreifer", password="uebernahme1")
        assert response.status_code == 409

        # Das erste Konto gilt weiterhin
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "benjamin", "password": "geheim123"},
            ).status_code
            == 200
        )

    def test_rejected_when_env_password_set(self, client, monkeypatch):
        monkeypatch.setenv("SSA_ADMIN_PASSWORD", "aus-der-umgebung")

        assert _setup(client).status_code == 409
        # Nichts geschrieben - sonst würde das Konto scharf, sobald der
        # Betreiber die Umgebungsvariable wieder entfernt.
        assert jobs_store.get_meta(ADMIN_PASSWORD_HASH_KEY) is None

    def test_survives_restart(self, client, tmp_path, monkeypatch):
        _setup(client)

        # Neustart simulieren: Store neu aufsetzen, Key-Cache leeren
        initialize_jobs_store(tmp_path / "test.db")
        reset_key_cache()

        response = client.post(
            "/api/auth/login", json={"username": "benjamin", "password": "geheim123"}
        )
        assert response.status_code == 200

    def test_username_is_trimmed(self, client):
        assert _setup(client, username="  benjamin  ").status_code == 200
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "benjamin", "password": "geheim123"},
            ).status_code
            == 200
        )

    @pytest.mark.parametrize(
        "payload",
        [
            {"username": "benjamin", "password": "kurz"},
            {"username": "", "password": "geheim123"},
            {"username": "   ", "password": "geheim123"},
            {"username": "benjamin", "password": "x" * 2000},
            {"username": "benjamin"},
        ],
    )
    def test_invalid_payload_422(self, client, payload):
        assert client.post("/api/auth/setup", json=payload).status_code == 422


class TestSetupToken:
    @pytest.fixture(autouse=True)
    def _token(self, client, monkeypatch):
        # Hängt bewusst an client: die Fixture räumt SSA_SETUP_TOKEN ab
        monkeypatch.setenv("SSA_SETUP_TOKEN", "richtiges-token")

    def test_status_announces_token(self, client):
        assert client.get("/api/auth/setup-status").json()["token_required"] is True

    def test_missing_token_403(self, client):
        assert _setup(client).status_code == 403

    def test_wrong_token_403(self, client):
        assert _setup(client, setup_token="falsch").status_code == 403

    def test_correct_token_succeeds(self, client):
        assert _setup(client, setup_token="richtiges-token").status_code == 200

    def test_403_not_401(self, client):
        # 401 würde im Frontend den globalen Logout auslösen und den
        # Setup-Bildschirm abräumen.
        assert _setup(client).status_code != 401


class TestSetupRateLimit:
    @pytest.fixture(autouse=True)
    def _short_limit(self, client, monkeypatch):
        monkeypatch.setenv("SSA_SETUP_TOKEN", "richtiges-token")
        # max_attempts wird beim Anlegen des Limiters aus der Umgebung gelesen,
        # der Singleton existiert zu diesem Zeitpunkt längst.
        monkeypatch.setattr(login_rate_limiter, "max_attempts", 3)
        login_rate_limiter.reset()

    def test_blocks_after_repeated_failures(self, client):
        for _ in range(3):
            assert _setup(client, setup_token="falsch").status_code == 403

        blocked = _setup(client, setup_token="richtiges-token")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

    def test_login_limit_is_separate(self, client):
        for _ in range(3):
            _setup(client, setup_token="falsch")

        # Der Login teilt sich das Kontingent nicht mit der Ersteinrichtung
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "x"}
            ).status_code
            == 503
        )
