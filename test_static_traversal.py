"""Sicherheitstests: Die SPA-Auslieferung darf keine Dateien ausserhalb von
frontend/dist herausgeben (Path Traversal).

Hintergrund: Die Catch-all-Route ist bewusst nicht authentifiziert. Sie verband
den vom Client kontrollierten Pfad direkt mit dem Frontend-Verzeichnis und prüfte
nur exists()/is_file(). URL-kodierte Dot-Segmente (%2e%2e%2f) werden vom
ASGI-Server nicht normalisiert und erreichten den Handler unverändert - damit
liessen sich beliebige Dateien lesen, im Docker-Layout u.a. data/secret.key
(Master-Key fuer Token-Signatur UND NAS-Passwort-Verschluesselung).
"""
import pytest
from fastapi.testclient import TestClient

from app.services.jobs_store import initialize_jobs_store
from app.services.security import reset_key_cache

SPA_MARKER = '<div id="root">'

# Pfade ausserhalb von frontend/dist, die niemals ausgeliefert werden duerfen
TRAVERSAL_PROBES = [
    "../../requirements.txt",
    "..%2f..%2frequirements.txt",
    "%2e%2e%2f%2e%2e%2frequirements.txt",
    "..%2F..%2Frequirements.txt",
    "....%2f%2f....%2f%2frequirements.txt",
    "..%2f..%2fapp%2fservices%2fsecurity.py",
    "..%2f..%2fdata%2fsecret.key",
    "..%2f..%2f..%2fetc%2fpasswd",
    "assets%2f..%2f..%2f..%2frequirements.txt",
]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    monkeypatch.setenv("SSA_ADMIN_PASSWORD", "testpass123")
    reset_key_cache()

    import app.services.storage as storage_module

    test_storage = storage_module.ScanStorage(
        db_path=tmp_path / "test.db", auto_cleanup_enabled=False
    )
    monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
    initialize_jobs_store(tmp_path / "test.db")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    reset_key_cache()


@pytest.mark.parametrize("probe", TRAVERSAL_PROBES)
def test_traversal_does_not_leak_files(client, probe):
    """Kein Dateiinhalt ausserhalb von frontend/dist - egal wie kodiert"""
    response = client.get(f"/{probe}")

    # Zulaessig ist nur: 404 oder der SPA-Fallback (index.html)
    assert response.status_code in (200, 404), response.status_code
    if response.status_code == 200:
        assert SPA_MARKER in response.text, (
            f"Traversal '{probe}' lieferte HTTP 200 mit Fremdinhalt statt der SPA"
        )

    body = response.text.lower()
    for leaked in ("uvicorn>=", "apscheduler>=", "ssa_secret_key", "root:x:0:0"):
        assert leaked not in body, f"Traversal '{probe}' hat '{leaked}' geleakt"


def test_legitimate_asset_still_served(client):
    """Der Fix darf die normale Auslieferung nicht kaputtmachen"""
    response = client.get("/index.html")
    assert response.status_code == 200
    assert SPA_MARKER in response.text


def test_spa_fallback_still_works(client):
    """Unbekannte Routen liefern weiterhin die SPA (React Router)"""
    response = client.get("/irgendeine/client/route")
    assert response.status_code == 200
    assert SPA_MARKER in response.text


def test_api_and_health_not_shadowed(client):
    """Die Catch-all darf API und Health nicht verschatten"""
    assert client.get("/health").status_code == 200
    assert client.get("/api/scans").status_code == 401  # Auth, nicht 404
