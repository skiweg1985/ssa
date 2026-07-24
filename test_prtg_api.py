"""Tests für die PRTG-"HTTP Data Advanced"-Endpoints.

Kernpunkte: Schema-Konformität (alle Werte sind Strings, float-Flag genau bei
Dezimalwerten), Zugriff durch Monitoring-API-Tokens, Fehlerfälle und der
Kanal-Cap.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.jobs_store import initialize_jobs_store
from app.services.security import reset_key_cache

# Felder, die ein PRTG-Kanal haben darf (Paessler-Referenz)
ALLOWED_CHANNEL_KEYS = {
    "channel", "value", "unit", "customunit", "float", "mode", "decimalmode",
    "valuelookup", "volumesize", "speedsize", "speedtime", "showchart",
    "showtable", "warning", "limitmode", "limitminwarning", "limitmaxwarning",
    "limitwarningmsg", "limitminerror", "limitmaxerror", "limiterrormsg",
}


# ----------------------------------------------------------------------
# Schema-Helfer
# ----------------------------------------------------------------------

def assert_prtg_schema(body):
    """Prüft die harten Schema-Regeln von PRTG"""
    assert set(body.keys()) == {"prtg"}, "Wurzel darf nur 'prtg' enthalten"
    prtg = body["prtg"]
    assert set(prtg.keys()) <= {"result", "text", "error"}

    for key in ("text", "error"):
        if key in prtg:
            assert isinstance(prtg[key], str), f"prtg.{key} muss ein String sein"

    for channel in prtg.get("result", []):
        assert "channel" in channel and "value" in channel
        unknown = set(channel.keys()) - ALLOWED_CHANNEL_KEYS
        assert not unknown, f"Unbekannte Kanalfelder: {unknown}"
        for key, value in channel.items():
            assert isinstance(value, str), (
                f"Kanal '{channel['channel']}': {key}={value!r} ist kein String "
                "- PRTG erwartet ausschliesslich Strings"
            )
            assert value is not None


def assert_float_flags(body):
    """Dezimalwerte MÜSSEN float='1' tragen, sonst zeigt PRTG 0 an"""
    for channel in body["prtg"].get("result", []):
        has_decimals = "." in channel["value"]
        has_flag = channel.get("float") == "1"
        assert has_decimals == has_flag, (
            f"Kanal '{channel['channel']}' (value={channel['value']}): "
            f"float-Flag {'fehlt' if has_decimals else 'faelschlich gesetzt'}"
        )


def channels_by_name(body):
    return {c["channel"]: c for c in body["prtg"].get("result", [])}


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

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


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "testpass123"}
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def api_token_headers(client, auth_headers):
    response = client.post(
        "/api/api-tokens", headers=auth_headers, json={"name": "PRTG"}
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _make_result(timestamp=None, status="completed", folders=None, error=None):
    if folders is None:
        folders = [("/design", 1073741824), ("/photo", 500000000)]
    return ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=timestamp or datetime.now(timezone.utc),
        status=status,
        error=error,
        results=[
            ScanResultItem(
                folder_name=name,
                success=True,
                num_dir=10,
                num_file=100,
                total_size=TotalSize(bytes=size, formatted=1.0, unit="GB"),
                elapsed_time_ms=12530,
            )
            for name, size in folders
        ],
    )


@pytest.fixture
def seeded_job(client, auth_headers, monkeypatch):
    """Legt Verbindung + Job an und speichert einen erfolgreichen Lauf"""
    import app.services.storage as storage_module

    connection = client.post(
        "/api/nas-connections",
        headers=auth_headers,
        json={"name": "NAS", "host": "nas.local", "username": "u", "password": "p"},
    ).json()
    job = client.post(
        "/api/scan-jobs",
        headers=auth_headers,
        json={
            "name": "Design Scan",
            "nas_connection_id": connection["id"],
            "paths": ["/design", "/photo"],
            "interval": "6h",
            "enabled": True,
        },
    ).json()
    storage_module._storage_instance.add_result(
        job["slug"], job["name"], _make_result(), "nas.local"
    )
    return job


# ----------------------------------------------------------------------
# Job-Sensor
# ----------------------------------------------------------------------

class TestScanSensor:
    def test_schema_and_float_flags(self, client, auth_headers, seeded_job):
        response = client.get("/api/prtg/scans/design-scan", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert_prtg_schema(body)
        assert_float_flags(body)
        assert "error" not in body["prtg"]

    def test_expected_channels(self, client, auth_headers, seeded_job):
        body = client.get("/api/prtg/scans/design-scan", headers=auth_headers).json()
        channels = channels_by_name(body)
        for name in (
            "Gesamtgröße", "Ordner", "Dateien", "Scan-Dauer",
            "Alter letzter Lauf", "Alter letzte Daten", "Status",
            "Ordner OK", "Ordner Fehler",
        ):
            assert name in channels, f"Kanal '{name}' fehlt"
        assert channels["Gesamtgröße"]["value"] == str(1073741824 + 500000000)
        assert channels["Gesamtgröße"]["unit"] == "BytesDisk"
        assert channels["Ordner OK"]["value"] == "2"
        assert channels["Status"]["value"] == "0"

    def test_scan_duration_is_float(self, client, auth_headers, seeded_job):
        channels = channels_by_name(
            client.get("/api/prtg/scans/design-scan", headers=auth_headers).json()
        )
        duration = channels["Scan-Dauer"]
        assert duration["float"] == "1"
        assert "." in duration["value"]
        assert duration["unit"] == "TimeSeconds"

    def test_folder_channels(self, client, auth_headers, seeded_job):
        channels = channels_by_name(
            client.get("/api/prtg/scans/design-scan", headers=auth_headers).json()
        )
        assert channels["/design"]["value"] == "1073741824"
        assert channels["/photo"]["value"] == "500000000"

    def test_folders_can_be_disabled(self, client, auth_headers, seeded_job):
        body = client.get(
            "/api/prtg/scans/design-scan?folders=0", headers=auth_headers
        ).json()
        assert not [
            c for c in body["prtg"]["result"] if c["channel"].startswith("/")
        ]

    def test_limits_can_be_disabled(self, client, auth_headers, seeded_job):
        body = client.get(
            "/api/prtg/scans/design-scan?limits=0", headers=auth_headers
        ).json()
        for channel in body["prtg"]["result"]:
            assert not [k for k in channel if k.startswith("limit")], (
                f"Kanal '{channel['channel']}' enthaelt Limits trotz limits=0"
            )

    def test_channel_cap(self, client, auth_headers, monkeypatch):
        """Mehr Ordner als erlaubt -> Cap greift, Hinweis im Text, <= 50 Kanaele"""
        import app.services.storage as storage_module

        connection = client.post(
            "/api/nas-connections",
            headers=auth_headers,
            json={"name": "N", "host": "h", "username": "u", "password": "p"},
        ).json()
        paths = [f"/ordner{i:03d}" for i in range(60)]
        job = client.post(
            "/api/scan-jobs",
            headers=auth_headers,
            json={
                "name": "Viele Ordner",
                "nas_connection_id": connection["id"],
                "paths": paths,
                "interval": "6h",
                "enabled": True,
            },
        ).json()
        storage_module._storage_instance.add_result(
            job["slug"],
            job["name"],
            _make_result(folders=[(p, 1000) for p in paths]),
            "h",
        )

        body = client.get(
            f"/api/prtg/scans/{job['slug']}?max_folders=5", headers=auth_headers
        ).json()
        assert_prtg_schema(body)
        folder_channels = [
            c for c in body["prtg"]["result"] if c["channel"].startswith("/ordner")
        ]
        assert len(folder_channels) == 5
        assert len(body["prtg"]["result"]) <= 50
        assert "60" in body["prtg"]["text"]

    def test_default_cap_respects_prtg_limit(self, client, auth_headers):
        """Auch ohne max_folders duerfen nie mehr als 50 Kanaele entstehen"""
        import app.services.storage as storage_module

        connection = client.post(
            "/api/nas-connections",
            headers=auth_headers,
            json={"name": "N2", "host": "h2", "username": "u", "password": "p"},
        ).json()
        paths = [f"/p{i:03d}" for i in range(80)]
        job = client.post(
            "/api/scan-jobs",
            headers=auth_headers,
            json={
                "name": "Sehr viele",
                "nas_connection_id": connection["id"],
                "paths": paths,
                "interval": "6h",
                "enabled": True,
            },
        ).json()
        storage_module._storage_instance.add_result(
            job["slug"], job["name"], _make_result(folders=[(p, 1) for p in paths]), "h2"
        )
        body = client.get(f"/api/prtg/scans/{job['slug']}", headers=auth_headers).json()
        assert len(body["prtg"]["result"]) <= 50

    def test_unknown_scan_returns_prtg_error(self, client, auth_headers):
        response = client.get("/api/prtg/scans/gibtsnicht", headers=auth_headers)
        assert response.status_code == 200, "PRTG erwartet Fehler im Body, nicht als HTTP-Status"
        body = response.json()
        assert_prtg_schema(body)
        assert body["prtg"]["error"] == "1"
        assert "gibtsnicht" in body["prtg"]["text"]
        assert "result" not in body["prtg"]

    def test_job_without_results_returns_prtg_error(self, client, auth_headers):
        connection = client.post(
            "/api/nas-connections",
            headers=auth_headers,
            json={"name": "N3", "host": "h3", "username": "u", "password": "p"},
        ).json()
        job = client.post(
            "/api/scan-jobs",
            headers=auth_headers,
            json={
                "name": "Frisch",
                "nas_connection_id": connection["id"],
                "paths": ["/neu"],
                "interval": "6h",
                "enabled": True,
            },
        ).json()
        body = client.get(f"/api/prtg/scans/{job['slug']}", headers=auth_headers).json()
        assert body["prtg"]["error"] == "1"
        assert "Ergebnisse" in body["prtg"]["text"]

    def test_failed_last_run_keeps_values_and_sets_status(
        self, client, auth_headers, seeded_job
    ):
        """Nach einem Fehllauf bleiben die Messwerte erhalten, Status wird 4"""
        import app.services.storage as storage_module

        storage_module._storage_instance.add_result(
            seeded_job["slug"],
            seeded_job["name"],
            ScanResult(
                scan_slug=seeded_job["slug"],
                scan_name=seeded_job["name"],
                timestamp=datetime.now(timezone.utc),
                status="failed",
                error="Login fehlgeschlagen",
                results=[],
            ),
            "nas.local",
        )
        body = client.get(
            f"/api/prtg/scans/{seeded_job['slug']}", headers=auth_headers
        ).json()
        channels = channels_by_name(body)
        assert channels["Status"]["value"] == "4"
        assert channels["Status"]["limitmaxerror"] == "3.5", (
            "Status 4 muss ueber dem Error-Limit liegen"
        )
        assert channels["Gesamtgröße"]["value"] == str(1073741824 + 500000000), (
            "Messwerte des letzten erfolgreichen Laufs muessen erhalten bleiben"
        )

    def test_disabled_job_has_no_age_limits(self, client, auth_headers, seeded_job):
        client.put(
            f"/api/scan-jobs/{seeded_job['slug']}",
            headers=auth_headers,
            json={
                "name": seeded_job["name"],
                "nas_connection_id": seeded_job["nas_connection_id"],
                "paths": seeded_job["paths"],
                "interval": seeded_job["interval"],
                "enabled": False,
            },
        )
        channels = channels_by_name(
            client.get(
                f"/api/prtg/scans/{seeded_job['slug']}", headers=auth_headers
            ).json()
        )
        assert channels["Status"]["value"] == "2"
        assert "limitmode" not in channels["Alter letzter Lauf"], (
            "Ein deaktivierter Job darf nicht wegen Alters rot werden"
        )

    def test_naive_timestamp_does_not_crash(self, client, auth_headers, seeded_job):
        """Regression: naive Timestamps (alte Daten) duerfen keinen 500 ausloesen"""
        import app.services.storage as storage_module

        storage_module._storage_instance.add_result(
            seeded_job["slug"],
            seeded_job["name"],
            _make_result(timestamp=datetime.utcnow()),  # naiv, ohne tzinfo
            "nas.local",
        )
        response = client.get(
            f"/api/prtg/scans/{seeded_job['slug']}", headers=auth_headers
        )
        assert response.status_code == 200
        assert_prtg_schema(response.json())
        assert "error" not in response.json()["prtg"]

    def test_age_limits_derived_from_interval(self, client, auth_headers, seeded_job):
        channels = channels_by_name(
            client.get(
                f"/api/prtg/scans/{seeded_job['slug']}", headers=auth_headers
            ).json()
        )
        age = channels["Alter letzter Lauf"]
        assert age["limitmode"] == "1"
        # 6h Intervall -> Warning bei 2x, Error bei 3x
        assert float(age["limitmaxwarning"]) == pytest.approx(6 * 3600 * 2)
        assert float(age["limitmaxerror"]) == pytest.approx(6 * 3600 * 3)


# ----------------------------------------------------------------------
# Server-Sensor
# ----------------------------------------------------------------------

class TestServerSensor:
    def test_schema_and_channels(self, client, auth_headers):
        response = client.get("/api/prtg/server", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert_prtg_schema(body)
        assert_float_flags(body)
        channels = channels_by_name(body)
        for name in (
            "Uptime", "Scheduler", "Jobs gesamt", "Jobs aktiv", "Scans laufend",
            "Jobs mit Fehler", "Jobs ohne Ergebnisse", "DB-Größe",
            "Ergebnisse in DB", "Konfigurationswarnungen",
        ):
            assert name in channels, f"Kanal '{name}' fehlt"

    def test_without_psutil_omits_system_channels(
        self, client, auth_headers, monkeypatch
    ):
        monkeypatch.setattr("app.services.health.PSUTIL_AVAILABLE", False)
        body = client.get("/api/prtg/server", headers=auth_headers).json()
        assert_prtg_schema(body)
        channels = channels_by_name(body)
        for name in ("CPU", "RAM belegt", "Disk belegt"):
            assert name not in channels, (
                "Ohne psutil duerfen keine 0-Werte als Systemkanaele erscheinen"
            )
        # Rest bleibt nutzbar, kein harter Fehler
        assert "Scheduler" in channels
        assert "error" not in body["prtg"]
        assert "psutil" in body["prtg"]["text"]

    def test_failed_jobs_counted(self, client, auth_headers, seeded_job):
        import app.services.storage as storage_module

        storage_module._storage_instance.add_result(
            seeded_job["slug"],
            seeded_job["name"],
            ScanResult(
                scan_slug=seeded_job["slug"],
                scan_name=seeded_job["name"],
                timestamp=datetime.now(timezone.utc),
                status="failed",
                error="kaputt",
                results=[],
            ),
            "nas.local",
        )
        channels = channels_by_name(
            client.get("/api/prtg/server", headers=auth_headers).json()
        )
        assert channels["Jobs mit Fehler"]["value"] == "1"
        assert channels["Jobs mit Fehler"]["limitmaxerror"] == "0.5"

    def test_limits_can_be_disabled(self, client, auth_headers):
        body = client.get("/api/prtg/server?limits=0", headers=auth_headers).json()
        for channel in body["prtg"]["result"]:
            assert not [k for k in channel if k.startswith("limit")]


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------

class TestPrtgAuth:
    def test_requires_auth(self, client):
        assert client.get("/api/prtg/server").status_code == 401
        assert client.get("/api/prtg/scans/irgendwas").status_code == 401

    def test_api_token_may_read(self, client, api_token_headers, seeded_job):
        assert client.get("/api/prtg/server", headers=api_token_headers).status_code == 200
        assert (
            client.get(
                f"/api/prtg/scans/{seeded_job['slug']}", headers=api_token_headers
            ).status_code
            == 200
        )

    def test_api_token_still_blocked_on_management(self, client, api_token_headers):
        assert (
            client.get("/api/nas-connections", headers=api_token_headers).status_code
            == 403
        )
        assert client.get("/api/api-tokens", headers=api_token_headers).status_code == 403


# ----------------------------------------------------------------------
# /health-Vertrag (nach der Extraktion nach services/health.py)
# ----------------------------------------------------------------------

def test_health_contract_unchanged(client):
    """Die /health-Antwort ist oeffentlicher Vertrag und darf sich nicht aendern"""
    body = client.get("/health").json()
    assert {"status", "timestamp", "server", "system", "scheduler", "storage", "scans"} <= set(
        body.keys()
    )
    assert {"version", "python_version", "platform", "platform_version"} <= set(
        body["server"].keys()
    )
    assert "uptime_seconds" in body["server"]
    assert {"running", "total_jobs", "enabled_jobs"} <= set(body["scheduler"].keys())
    assert {"scan_count", "db_size_mb", "db_path"} <= set(body["storage"].keys())
    assert {"total_configured", "enabled", "running", "running_scans"} <= set(
        body["scans"].keys()
    )
