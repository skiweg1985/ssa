"""Tests für die Auth-Durchsetzung der API (Login, Token, offene Endpoints)"""
import pytest
from fastapi.testclient import TestClient

from app.services.jobs_store import initialize_jobs_store
from app.services.security import reset_key_cache


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    monkeypatch.setenv("SSA_ADMIN_PASSWORD", "testpass123")
    reset_key_cache()

    # Storage auf temporäre DB umbiegen - der App-Lifespan initialisiert den
    # Jobs-Store mit storage.db_path, daher muss auch der Storage auf tmp zeigen
    # (sonst würden Tests in die echte data/history.db schreiben).
    import app.services.storage as storage_module

    test_storage = storage_module.ScanStorage(db_path=tmp_path / "test.db")
    monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
    initialize_jobs_store(tmp_path / "test.db")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    reset_key_cache()


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "testpass123"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


class TestAuthEnforcement:
    def test_scans_requires_token(self, client):
        assert client.get("/api/scans").status_code == 401

    def test_nas_connections_requires_token(self, client):
        assert client.get("/api/nas-connections").status_code == 401

    def test_scan_jobs_requires_token(self, client):
        assert client.get("/api/scan-jobs").status_code == 401

    def test_storage_requires_token(self, client):
        assert client.get("/api/storage/stats").status_code == 401

    def test_invalid_token_rejected(self, client):
        response = client.get(
            "/api/scans", headers={"Authorization": "Bearer kaputt"}
        )
        assert response.status_code == 401

    def test_health_is_open(self, client):
        assert client.get("/health").status_code == 200

    def test_valid_token_grants_access(self, client, auth_headers):
        assert client.get("/api/scans", headers=auth_headers).status_code == 200


class TestLogin:
    def test_login_success_returns_token(self, client):
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "testpass123"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "admin"
        assert body["token"]
        assert body["expires_at"]

    def test_wrong_password_401(self, client):
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "falsch"}
        )
        assert response.status_code == 401

    def test_wrong_username_401(self, client):
        response = client.post(
            "/api/auth/login", json={"username": "root", "password": "testpass123"}
        )
        assert response.status_code == 401

    def test_unconfigured_password_503(self, client, monkeypatch):
        monkeypatch.delenv("SSA_ADMIN_PASSWORD", raising=False)
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "x"}
        )
        assert response.status_code == 503
        assert "SSA_ADMIN_PASSWORD" in response.json()["detail"]

    def test_me_with_token(self, client, auth_headers):
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["username"] == "admin"

    def test_me_without_token(self, client):
        assert client.get("/api/auth/me").status_code == 401


class TestJobApiValidation:
    def test_invalid_interval_422(self, client, auth_headers):
        conn = client.post(
            "/api/nas-connections",
            headers=auth_headers,
            json={"name": "N1", "host": "h", "username": "u", "password": "p"},
        ).json()
        response = client.post(
            "/api/scan-jobs",
            headers=auth_headers,
            json={
                "name": "Bad",
                "nas_connection_id": conn["id"],
                "paths": ["/x"],
                "interval": "kaputt",
                "enabled": True,
            },
        )
        assert response.status_code == 422
        assert "Intervall" in response.json()["detail"]

    def test_missing_connection_422(self, client, auth_headers):
        response = client.post(
            "/api/scan-jobs",
            headers=auth_headers,
            json={
                "name": "X",
                "nas_connection_id": 4242,
                "paths": ["/x"],
                "interval": "1h",
                "enabled": True,
            },
        )
        assert response.status_code == 422

    def test_no_paths_422(self, client, auth_headers):
        conn = client.post(
            "/api/nas-connections",
            headers=auth_headers,
            json={"name": "N2", "host": "h", "username": "u", "password": "p"},
        ).json()
        response = client.post(
            "/api/scan-jobs",
            headers=auth_headers,
            json={
                "name": "Leer",
                "nas_connection_id": conn["id"],
                "interval": "1h",
                "enabled": True,
            },
        )
        assert response.status_code == 422

    def test_api_token_lifecycle_and_scope(self, client, auth_headers):
        """API-Token: erstellen -> read-only Zugriff -> Scope-Grenzen -> widerrufen"""
        # Erstellen (nur mit Login möglich)
        response = client.post(
            "/api/api-tokens", headers=auth_headers, json={"name": "PRTG"}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["token"].startswith("ssa_")
        token_headers = {"Authorization": f"Bearer {body['token']}"}
        token_id = body["id"]

        # Liste enthält NIE den Klartext-Token
        listing = client.get("/api/api-tokens", headers=auth_headers).json()
        assert all("token" not in t for t in listing)
        assert listing[0]["name"] == "PRTG"

        # GET auf Monitoring-Endpoints erlaubt
        assert client.get("/api/scans", headers=token_headers).status_code == 200
        assert client.get("/api/storage/stats", headers=token_headers).status_code == 200

        # Schreibende/verwaltende Zugriffe verboten (403)
        assert (
            client.post(
                "/api/scan-jobs",
                headers=token_headers,
                json={
                    "name": "X",
                    "nas_connection_id": 1,
                    "paths": ["/x"],
                    "interval": "1h",
                    "enabled": True,
                },
            ).status_code
            == 403
        )
        assert (
            client.get("/api/nas-connections", headers=token_headers).status_code == 403
        )
        assert client.get("/api/api-tokens", headers=token_headers).status_code == 403
        assert (
            client.post(
                "/api/scans/egal/trigger", headers=token_headers
            ).status_code
            == 403
        )

        # last_used_at wurde gesetzt
        listing = client.get("/api/api-tokens", headers=auth_headers).json()
        assert listing[0]["last_used_at"] is not None

        # Widerrufen -> Token sofort ungültig
        assert (
            client.delete(
                f"/api/api-tokens/{token_id}", headers=auth_headers
            ).status_code
            == 204
        )
        assert client.get("/api/scans", headers=token_headers).status_code == 401

    def test_api_token_duplicate_name_409(self, client, auth_headers):
        client.post("/api/api-tokens", headers=auth_headers, json={"name": "Doppelt"})
        response = client.post(
            "/api/api-tokens", headers=auth_headers, json={"name": "Doppelt"}
        )
        assert response.status_code == 409

    def test_connection_response_never_contains_password(self, client, auth_headers):
        response = client.post(
            "/api/nas-connections",
            headers=auth_headers,
            json={"name": "N3", "host": "h", "username": "u", "password": "geheim"},
        )
        assert response.status_code == 201
        assert "password" not in response.json()
        listing = client.get("/api/nas-connections", headers=auth_headers).json()
        assert all("password" not in c for c in listing)
        assert "geheim" not in response.text
