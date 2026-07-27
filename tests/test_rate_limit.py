"""Tests für den Brute-Force-Schutz am Login-Endpoint"""
import pytest
from fastapi.testclient import TestClient

from app.services.jobs_store import initialize_jobs_store
from app.services.rate_limit import LoginRateLimiter, login_rate_limiter
from app.services.security import reset_key_cache


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    monkeypatch.setenv("SSA_ADMIN_PASSWORD", "testpass123")
    reset_key_cache()
    login_rate_limiter.reset()

    import app.services.storage as storage_module

    test_storage = storage_module.ScanStorage(
        db_path=tmp_path / "test.db", auto_cleanup_enabled=False
    )
    monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
    initialize_jobs_store(tmp_path / "test.db")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    login_rate_limiter.reset()
    reset_key_cache()


def _login(client, password="falsch"):
    return client.post(
        "/api/auth/login", json={"username": "admin", "password": password}
    )


class TestLoginRateLimitApi:
    def test_blocks_after_max_attempts(self, client):
        """Nach 5 Fehlversuchen greift die Sperre mit 429 + Retry-After"""
        for i in range(4):
            assert _login(client).status_code == 401, f"Versuch {i + 1}"

        blocked = _login(client)
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert int(blocked.headers["Retry-After"]) > 0

        # Auch mit RICHTIGEM Passwort bleibt gesperrt
        assert _login(client, "testpass123").status_code == 429

    def test_successful_login_resets_counter(self, client):
        """Ein erfolgreicher Login darf den Zaehler leeren"""
        for _ in range(3):
            assert _login(client).status_code == 401

        assert _login(client, "testpass123").status_code == 200

        # Zaehler ist zurueckgesetzt -> wieder 4 Fehlversuche moeglich
        for i in range(4):
            assert _login(client).status_code == 401, f"nach Reset, Versuch {i + 1}"

    def test_unblocked_client_can_still_log_in(self, client):
        """Ein Client ohne Fehlversuche wird nicht beeintraechtigt"""
        assert _login(client, "testpass123").status_code == 200


class TestLoginRateLimiter:
    def test_allows_until_limit(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, block_seconds=10)
        for _ in range(2):
            assert limiter.register_failure("ip") == (False, 0)
        blocked, duration = limiter.register_failure("ip")
        assert blocked is True
        assert duration == 10
        assert limiter.check("ip")[0] is False

    def test_progressive_block_doubles(self):
        """Wiederholte Sperren verlaengern sich progressiv"""
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60, block_seconds=10)
        assert limiter.register_failure("ip")[1] == 10
        assert limiter.register_failure("ip")[1] == 20
        assert limiter.register_failure("ip")[1] == 40

    def test_block_duration_is_capped(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60, block_seconds=1000)
        durations = [limiter.register_failure("ip")[1] for _ in range(6)]
        assert max(durations) <= 3600, "Sperre muss gedeckelt sein"

    def test_window_expiry_resets_failures(self, monkeypatch):
        """Fehlversuche ausserhalb des Zeitfensters zaehlen nicht mehr mit"""
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, block_seconds=10)
        now = [1000.0]
        monkeypatch.setattr("app.services.rate_limit.time.time", lambda: now[0])

        limiter.register_failure("ip")
        limiter.register_failure("ip")
        now[0] += 61  # Fenster abgelaufen
        assert limiter.register_failure("ip") == (False, 0), (
            "alte Fehlversuche duerfen nach Fensterablauf nicht mehr zaehlen"
        )

    def test_block_expires(self, monkeypatch):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60, block_seconds=10)
        now = [1000.0]
        monkeypatch.setattr("app.services.rate_limit.time.time", lambda: now[0])

        limiter.register_failure("ip")
        assert limiter.check("ip")[0] is False
        now[0] += 11
        assert limiter.check("ip")[0] is True

    def test_clients_are_independent(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60, block_seconds=10)
        limiter.register_failure("ip-a")
        assert limiter.check("ip-a")[0] is False
        assert limiter.check("ip-b")[0] is True, "andere Clients duerfen nicht mitgesperrt werden"

    def test_success_clears_block_level(self):
        limiter = LoginRateLimiter(max_attempts=1, window_seconds=60, block_seconds=10)
        limiter.register_failure("ip")
        limiter.register_success("ip")
        assert limiter.check("ip")[0] is True
        # Sperrstufe ist zurueckgesetzt -> wieder Basisdauer
        assert limiter.register_failure("ip")[1] == 10
