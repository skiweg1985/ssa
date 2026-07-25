"""Tests für die NAS-Systemmetriken (Kapazität via File Station, Health via SNMP).

Schwerpunkte:
- Volume-Deduplizierung: mehrere Freigaben auf einem Volume zählen einmal
- PRTG-Schemakonformität der beiden neuen Sensoren
- Quellentrennung: eine ausgefallene Quelle reißt die andere nicht mit
- Auth: /api/nas-metrics ist für Monitoring-Tokens offen,
  /api/nas-connections bleibt es ausdrücklich NICHT
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.services.jobs_store import initialize_jobs_store
from app.services.security import reset_key_cache
from test_prtg_api import (  # wiederverwendete Schema-Helfer
    assert_float_flags,
    assert_prtg_schema,
    channels_by_name,
)


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

    import app.services.nas_metrics as metrics_module
    import app.services.nas_session as session_module

    metrics_module.clear_cache()
    session_module.clear_sessions()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    metrics_module.clear_cache()
    session_module.clear_sessions()
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


@pytest.fixture
def connection(client, auth_headers):
    return client.post(
        "/api/nas-connections",
        headers=auth_headers,
        json={"name": "NAS-01", "host": "nas.local", "username": "u", "password": "p"},
    ).json()


SHARES = [
    {
        "name": "video",
        "additional": {
            "real_path": "/volume1/video",
            "volume_status": {"freespace": 100_000, "totalspace": 1_000_000, "readonly": False},
            "perm": {"write": True},
        },
    },
    {
        "name": "music",
        "additional": {
            "real_path": "/volume1/music",
            "volume_status": {"freespace": 100_000, "totalspace": 1_000_000, "readonly": False},
            "perm": {"write": True},
        },
    },
    {
        "name": "backup",
        "additional": {
            "real_path": "/volume1/backup",
            "volume_status": {"freespace": 100_000, "totalspace": 1_000_000, "readonly": False},
            "perm": {"write": True},
        },
    },
    {
        "name": "archiv",
        "additional": {
            "real_path": "/volume2/archiv",
            "volume_status": {"freespace": 0, "totalspace": 500_000, "readonly": True},
            "perm": {"write": False},
        },
    },
]

HEALTH = {
    "system": {
        "model_name": "DS920+",
        "dsm_version": "DSM 7.2",
        "system_status": "ok",
        "system_status_label": "Normal",
        "power_status": "ok",
        "system_fan_status": "ok",
        "cpu_fan_status": "ok",
        "temperature_celsius": 41.0,
        "upgrade_available": False,
        "cpu_percent": 12.5,
        "memory_total_bytes": 8_000_000_000,
        "memory_available_bytes": 4_000_000_000,
        "memory_used_percent": 50.0,
    },
    "disks": [
        {"name": "Drive 1", "model": "ST4000", "status": "ok",
         "status_label": "Normal", "temperature_celsius": 38.0},
        {"name": "Drive 2", "model": "WD40", "status": "error",
         "status_label": "Crashed", "temperature_celsius": 58.0},
    ],
    "raids": [
        {"name": "Volume 1", "status": "error", "status_label": "Degrade",
         "total_bytes": 1_000_000, "free_bytes": 250_000, "used_percent": 75.0},
    ],
    "ups": None,
    "response_seconds": 0.2,
}


@pytest.fixture
def mock_capacity(monkeypatch):
    """list_shared_folders liefert SHARES, ohne dass ein NAS existiert"""
    import app.services.nas_metrics as metrics_module

    class FakeAPI:
        def list_shared_folders(self, show_message=False):
            return list(SHARES)

    async def fake_get_session(connection_id):
        return FakeAPI()

    monkeypatch.setattr(metrics_module, "get_session", fake_get_session)
    metrics_module.clear_cache()


@pytest.fixture
def mock_health(monkeypatch):
    """SNMP-Antwort ohne echtes NAS; aktiviert SNMP an Verbindung 1"""
    import app.services.nas_metrics as metrics_module

    monkeypatch.setattr(
        metrics_module.jobs_store,
        "get_snmp_config",
        lambda cid: {"host": "nas.local", "port": 161, "version": "2c",
                     "secrets": {"community": "public"}},
    )

    async def fake_collect(config):
        return {k: v for k, v in HEALTH.items() if k != "response_seconds"}

    import app.services.snmp_client as snmp_module

    monkeypatch.setattr(snmp_module, "collect_snmp_health", fake_collect)
    metrics_module.clear_cache()


# ----------------------------------------------------------------------
# Auswertung der Freigaben (ohne Netzwerk)
# ----------------------------------------------------------------------

class TestParseShares:
    def test_volumes_are_deduplicated(self):
        from app.services.nas_metrics import parse_shares

        result = parse_shares(SHARES)
        assert len(result["volumes"]) == 2, (
            "Drei Freigaben auf /volume1 müssen zu EINEM Volume verschmelzen - "
            "sonst wird derselbe Speicher mehrfach gezählt"
        )
        volume1 = result["volumes"][0]
        assert volume1["name"] == "volume1"
        assert volume1["share_count"] == 3
        assert volume1["total_bytes"] == 1_000_000
        assert volume1["used_percent"] == 90.0

    def test_readonly_and_permissions(self):
        from app.services.nas_metrics import parse_shares

        result = parse_shares(SHARES)
        assert result["share_count"] == 4
        assert result["shares_without_write"] == 1
        assert [v["readonly"] for v in result["volumes"]] == [False, True]

    def test_shares_without_volume_status_are_counted_but_skipped(self):
        from app.services.nas_metrics import parse_shares

        result = parse_shares(SHARES + [{"name": "leer", "additional": {}}])
        assert result["share_count"] == 5
        assert len(result["volumes"]) == 2

    def test_virtual_mounts_are_counted(self):
        from app.services.nas_metrics import parse_shares

        shares = SHARES + [
            {"name": "extern", "additional": {"mount_point_type": "cifs"}}
        ]
        assert parse_shares(shares)["virtual_mounts"] == 1

    def test_volumes_are_sorted_for_stable_channel_names(self):
        from app.services.nas_metrics import parse_shares

        names = [v["name"] for v in parse_shares(list(reversed(SHARES)))["volumes"]]
        assert names == sorted(names)


# ----------------------------------------------------------------------
# Generischer JSON-Endpoint
# ----------------------------------------------------------------------

class TestGenericEndpoint:
    def test_single_system_by_id(self, client, auth_headers, connection, mock_capacity):
        response = client.get(
            f"/api/nas-metrics/{connection['id']}?groups=capacity", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["connection_id"] == connection["id"]
        assert body["sources"]["filestation"]["available"] is True
        assert len(body["sources"]["filestation"]["data"]["volumes"]) == 2

    def test_single_system_by_name(self, client, auth_headers, connection, mock_capacity):
        response = client.get("/api/nas-metrics/NAS-01?groups=capacity", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "NAS-01"

    def test_list_all_systems(self, client, auth_headers, connection, mock_capacity):
        response = client.get("/api/nas-metrics?groups=capacity", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_filter_by_connection_id(self, client, auth_headers, connection, mock_capacity):
        response = client.get(
            f"/api/nas-metrics?connection_id={connection['id']}&groups=capacity",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_unknown_system_is_404(self, client, auth_headers):
        assert client.get("/api/nas-metrics/gibtsnicht", headers=auth_headers).status_code == 404

    def test_invalid_group_is_422(self, client, auth_headers, connection):
        response = client.get("/api/nas-metrics?groups=quatsch", headers=auth_headers)
        assert response.status_code == 422

    def test_unrequested_source_is_null_not_missing(
        self, client, auth_headers, connection, mock_capacity
    ):
        """
        Die Antwortstruktur bleibt konstant, egal was angefragt wurde.

        Sonst müssten Clients zwischen "Feld fehlt" und "Wert ist null"
        unterscheiden - je nach Abfrage und NAS-Modell.
        """
        body = client.get(
            f"/api/nas-metrics/{connection['id']}?groups=capacity", headers=auth_headers
        ).json()
        assert "snmp" in body["sources"]
        assert body["sources"]["snmp"] is None

    def test_snmp_failure_does_not_break_capacity(
        self, client, auth_headers, connection, mock_capacity
    ):
        """Ohne SNMP-Zugang bleiben die Kapazitätswerte vollständig"""
        body = client.get(
            f"/api/nas-metrics/{connection['id']}", headers=auth_headers
        ).json()
        assert body["sources"]["filestation"]["available"] is True
        assert body["sources"]["snmp"]["available"] is False
        assert body["sources"]["snmp"]["error"]

    def test_capacity_failure_does_not_break_snmp(
        self, client, auth_headers, connection, mock_health, monkeypatch
    ):
        import app.services.nas_metrics as metrics_module

        async def broken_session(connection_id):
            raise metrics_module.NASSessionError("NAS nicht erreichbar")

        monkeypatch.setattr(metrics_module, "get_session", broken_session)

        body = client.get(
            f"/api/nas-metrics/{connection['id']}", headers=auth_headers
        ).json()
        assert body["sources"]["filestation"]["available"] is False
        assert body["sources"]["snmp"]["available"] is True

    def test_response_contains_no_secrets(
        self, client, auth_headers, connection, mock_capacity, mock_health
    ):
        raw = client.get(
            f"/api/nas-metrics/{connection['id']}", headers=auth_headers
        ).text
        for secret in ("password", "public", "community", "snmp_secrets"):
            assert secret not in raw.lower(), f"'{secret}' darf nicht in der Antwort stehen"


# ----------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------

class TestCache:
    def test_second_request_is_served_from_cache(
        self, client, auth_headers, connection, monkeypatch
    ):
        """Zwei Sensoren am selben NAS dürfen nur EINEN Abruf auslösen"""
        import app.services.nas_metrics as metrics_module

        calls = []

        class FakeAPI:
            def list_shared_folders(self, show_message=False):
                calls.append(1)
                return list(SHARES)

        async def fake_get_session(connection_id):
            return FakeAPI()

        monkeypatch.setattr(metrics_module, "get_session", fake_get_session)
        metrics_module.clear_cache()

        url = f"/api/nas-metrics/{connection['id']}?groups=capacity"
        first = client.get(url, headers=auth_headers).json()
        second = client.get(url, headers=auth_headers).json()

        assert len(calls) == 1, "Der zweite Abruf muss aus dem Cache kommen"
        assert first["cached"] is False
        assert second["cached"] is True

    def test_errors_are_not_cached(self, client, auth_headers, connection, monkeypatch):
        """Ein kurzzeitig gestörtes NAS muss sich sofort erholen können"""
        import app.services.nas_metrics as metrics_module

        state = {"fail": True}

        class FakeAPI:
            def list_shared_folders(self, show_message=False):
                if state["fail"]:
                    raise RuntimeError("Netzwerkfehler")
                return list(SHARES)

        async def fake_get_session(connection_id):
            return FakeAPI()

        monkeypatch.setattr(metrics_module, "get_session", fake_get_session)
        metrics_module.clear_cache()

        url = f"/api/nas-metrics/{connection['id']}?groups=capacity"
        assert client.get(url, headers=auth_headers).json()[
            "sources"]["filestation"]["available"] is False

        state["fail"] = False
        assert client.get(url, headers=auth_headers).json()[
            "sources"]["filestation"]["available"] is True


# ----------------------------------------------------------------------
# PRTG: Kapazitäts-Sensor
# ----------------------------------------------------------------------

class TestCapacitySensor:
    def test_schema_and_float_flags(self, client, auth_headers, connection, mock_capacity):
        response = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert_prtg_schema(body)
        assert_float_flags(body)
        assert "error" not in body["prtg"]

    def test_expected_channels(self, client, auth_headers, connection, mock_capacity):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=auth_headers
        ).json()
        channels = channels_by_name(body)
        for name in (
            "Volumes", "Volumes schreibgeschützt", "Freigaben",
            "Freigaben ohne Schreibrecht", "Antwortzeit",
            "volume1 Belegung", "volume1 frei", "volume1 gesamt",
            "volume2 Belegung",
        ):
            assert name in channels, f"Kanal '{name}' fehlt"
        assert channels["Volumes"]["value"] == "2"
        assert channels["Freigaben"]["value"] == "4"
        assert channels["volume1 Belegung"]["value"] == "90.0"

    def test_readonly_volume_triggers_error_limit(
        self, client, auth_headers, connection, mock_capacity
    ):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=auth_headers
        ).json()
        channel = channels_by_name(body)["Volumes schreibgeschützt"]
        assert channel["value"] == "1"
        assert channel["limitmaxerror"] == "0.5"

    def test_volumes_can_be_disabled(self, client, auth_headers, connection, mock_capacity):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity?volumes=0", headers=auth_headers
        ).json()
        assert "volume1 Belegung" not in channels_by_name(body)

    def test_limits_can_be_disabled(self, client, auth_headers, connection, mock_capacity):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity?limits=0", headers=auth_headers
        ).json()
        for channel in body["prtg"]["result"]:
            assert "limitmode" not in channel

    def test_channel_cap_is_respected(
        self, client, auth_headers, connection, monkeypatch
    ):
        """Viele Volumes dürfen das 50-Kanal-Limit von PRTG nicht sprengen"""
        import app.services.nas_metrics as metrics_module

        many = [
            {
                "name": f"share{i:02d}",
                "additional": {
                    "real_path": f"/volume{i}/share{i:02d}",
                    "volume_status": {
                        "freespace": 100, "totalspace": 1000, "readonly": False
                    },
                },
            }
            for i in range(1, 31)
        ]

        class FakeAPI:
            def list_shared_folders(self, show_message=False):
                return many

        async def fake_get_session(connection_id):
            return FakeAPI()

        monkeypatch.setattr(metrics_module, "get_session", fake_get_session)
        metrics_module.clear_cache()

        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=auth_headers
        ).json()
        assert len(body["prtg"]["result"]) <= 50
        assert "nur 15 von 30 Volumes" in body["prtg"]["text"]

    def test_unreachable_nas_yields_prtg_error(
        self, client, auth_headers, connection, monkeypatch
    ):
        import app.services.nas_metrics as metrics_module

        async def broken(connection_id):
            raise metrics_module.NASSessionError("Zeitüberschreitung")

        monkeypatch.setattr(metrics_module, "get_session", broken)
        metrics_module.clear_cache()

        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=auth_headers
        ).json()
        assert body["prtg"]["error"] == "1"
        assert_prtg_schema(body)

    def test_unknown_connection_yields_prtg_error(self, client, auth_headers):
        body = client.get("/api/prtg/nas/gibtsnicht/capacity", headers=auth_headers).json()
        assert body["prtg"]["error"] == "1"

    def test_internal_details_are_not_leaked(
        self, client, auth_headers, connection, monkeypatch
    ):
        import app.services.nas_metrics as metrics_module

        async def broken(connection_id):
            raise RuntimeError("SELECT password_encrypted FROM nas_connections")

        monkeypatch.setattr(metrics_module, "get_session", broken)
        metrics_module.clear_cache()

        body = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=auth_headers
        ).json()
        assert "password_encrypted" not in body["prtg"]["text"]


# ----------------------------------------------------------------------
# PRTG: Health-Sensor
# ----------------------------------------------------------------------

class TestHealthSensor:
    def test_schema_and_float_flags(self, client, auth_headers, connection, mock_health):
        response = client.get(
            f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert_prtg_schema(body)
        assert_float_flags(body)
        assert "error" not in body["prtg"]

    def test_expected_channels(self, client, auth_headers, connection, mock_health):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
        ).json()
        channels = channels_by_name(body)
        for name in (
            "Systemstatus", "Temperatur", "Netzteil", "Systemlüfter", "CPU-Lüfter",
            "DSM-Update verfügbar", "Platten", "Platten nicht normal",
            "Höchste Plattentemperatur", "RAID-Verbünde", "RAID mit Fehler",
            "RAID in Wartung", "CPU", "RAM belegt", "Volume 1 Belegung",
        ):
            assert name in channels, f"Kanal '{name}' fehlt"
        assert channels["Platten"]["value"] == "2"
        assert channels["Platten nicht normal"]["value"] == "1"
        assert channels["Höchste Plattentemperatur"]["value"] == "58.0"

    def test_degraded_raid_is_an_error(self, client, auth_headers, connection, mock_health):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
        ).json()
        channel = channels_by_name(body)["RAID mit Fehler"]
        assert channel["value"] == "1"
        assert channel["limitmaxerror"] == "0.5"

    def test_busy_raid_warns_but_is_no_error(
        self, client, auth_headers, connection, mock_health, monkeypatch
    ):
        """RaidSyncing(7) ist Wartung - das darf keinen Fehler auslösen"""
        import app.services.nas_metrics as metrics_module
        import app.services.snmp_client as snmp_module

        async def busy(config):
            data = dict(HEALTH)
            data["raids"] = [
                {"name": "Volume 1", "status": "busy", "status_label": "RaidSyncing",
                 "total_bytes": 1000, "free_bytes": 500, "used_percent": 50.0}
            ]
            return data

        monkeypatch.setattr(snmp_module, "collect_snmp_health", busy)
        metrics_module.clear_cache()

        channels = channels_by_name(
            client.get(
                f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
            ).json()
        )
        assert channels["RAID mit Fehler"]["value"] == "0"
        assert channels["RAID in Wartung"]["value"] == "1"
        assert channels["RAID in Wartung"]["limitmaxwarning"] == "0.5"

    def test_status_channels_use_shared_scale(
        self, client, auth_headers, connection, mock_health
    ):
        channels = channels_by_name(
            client.get(
                f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
            ).json()
        )
        assert channels["Systemstatus"]["value"] == "0"  # ok
        assert channels["Systemstatus"]["limitmaxwarning"] == "1.5"
        assert channels["Systemstatus"]["limitmaxerror"] == "2.5"

    def test_disk_channels_are_opt_in(self, client, auth_headers, connection, mock_health):
        default = channels_by_name(
            client.get(
                f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
            ).json()
        )
        assert "Drive 1 Temperatur" not in default

        with_disks = channels_by_name(
            client.get(
                f"/api/prtg/nas/{connection['id']}/health?disks=1", headers=auth_headers
            ).json()
        )
        assert with_disks["Drive 1 Temperatur"]["value"] == "38.0"
        assert with_disks["Drive 2 Temperatur"]["value"] == "58.0"

    def test_missing_ups_yields_no_channels(
        self, client, auth_headers, connection, mock_health
    ):
        channels = channels_by_name(
            client.get(
                f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
            ).json()
        )
        assert "USV Batterie" not in channels

    def test_ups_channels_when_present(
        self, client, auth_headers, connection, mock_health, monkeypatch
    ):
        import app.services.nas_metrics as metrics_module
        import app.services.snmp_client as snmp_module

        async def with_ups(config):
            data = dict(HEALTH)
            data["ups"] = {
                "status": "OL", "battery_charge_percent": 100.0, "load_percent": 23.0
            }
            return data

        monkeypatch.setattr(snmp_module, "collect_snmp_health", with_ups)
        metrics_module.clear_cache()

        channels = channels_by_name(
            client.get(
                f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
            ).json()
        )
        assert channels["USV Batterie"]["value"] == "100.0"
        assert channels["USV Last"]["value"] == "23.0"

    def test_missing_values_are_omitted_not_reported_as_zero(
        self, client, auth_headers, connection, mock_health, monkeypatch
    ):
        """
        Nicht jedes Modell liefert Temperatur oder die UCD-MIB für CPU/RAM.

        Solche Kanäle werden weggelassen - als 0 gemeldet läsen sie sich wie
        echte Messwerte ("0 °C", "0 % CPU"). Zusätzlich verletzt ein Wert "0"
        mit float="1" die PRTG-Schemaregel.
        """
        import app.services.nas_metrics as metrics_module
        import app.services.snmp_client as snmp_module

        async def sparse(config):
            data = dict(HEALTH)
            data["system"] = {
                **HEALTH["system"],
                "temperature_celsius": None,
                "cpu_percent": None,
                "memory_used_percent": None,
            }
            data["disks"] = [
                {"name": "Drive 1", "model": None, "status": "ok",
                 "status_label": "Normal", "temperature_celsius": None}
            ]
            return data

        monkeypatch.setattr(snmp_module, "collect_snmp_health", sparse)
        metrics_module.clear_cache()

        body = client.get(
            f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
        ).json()
        assert_prtg_schema(body)
        assert_float_flags(body)

        channels = channels_by_name(body)
        for name in ("Temperatur", "CPU", "RAM belegt", "Höchste Plattentemperatur"):
            assert name not in channels, f"'{name}' ohne Messwert darf nicht erscheinen"
        # Die vorhandenen Statuskanäle bleiben davon unberührt
        assert channels["Systemstatus"]["value"] == "0"
        assert "ohne Temperatur" in body["prtg"]["text"]

    def test_snmp_not_configured_is_explained(self, client, auth_headers, connection):
        body = client.get(
            f"/api/prtg/nas/{connection['id']}/health", headers=auth_headers
        ).json()
        assert body["prtg"]["error"] == "1"
        assert "SNMP" in body["prtg"]["text"]

    def test_channel_count_stays_within_limit(
        self, client, auth_headers, connection, mock_health, monkeypatch
    ):
        import app.services.nas_metrics as metrics_module
        import app.services.snmp_client as snmp_module

        async def many_disks(config):
            data = dict(HEALTH)
            data["disks"] = [
                {"name": f"Drive {i}", "model": "X", "status": "ok",
                 "status_label": "Normal", "temperature_celsius": 40.0 + i}
                for i in range(1, 41)
            ]
            data["raids"] = [
                {"name": f"Volume {i}", "status": "ok", "status_label": "Normal",
                 "total_bytes": 1000, "free_bytes": 500, "used_percent": 50.0}
                for i in range(1, 11)
            ]
            return data

        monkeypatch.setattr(snmp_module, "collect_snmp_health", many_disks)
        metrics_module.clear_cache()

        body = client.get(
            f"/api/prtg/nas/{connection['id']}/health?disks=1", headers=auth_headers
        ).json()
        assert len(body["prtg"]["result"]) <= 50


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------

class TestAuth:
    def test_requires_token(self, client, connection):
        assert client.get("/api/nas-metrics").status_code == 401
        assert client.get(f"/api/prtg/nas/{connection['id']}/capacity").status_code == 401

    def test_api_token_may_read_metrics(
        self, client, api_token_headers, connection, mock_capacity
    ):
        response = client.get("/api/nas-metrics?groups=capacity", headers=api_token_headers)
        assert response.status_code == 200

    def test_api_token_may_read_prtg_sensors(
        self, client, api_token_headers, connection, mock_capacity
    ):
        response = client.get(
            f"/api/prtg/nas/{connection['id']}/capacity", headers=api_token_headers
        )
        assert response.status_code == 200

    def test_api_token_must_not_reach_nas_connections(
        self, client, api_token_headers, connection
    ):
        """
        Regressionstest für den Prefix-Fallstrick in app/api/deps.py.

        Die Whitelist vergleicht per startswith. Wäre dort "/api/nas" statt
        "/api/nas-metrics" eingetragen, bekäme jedes Monitoring-Token
        Lesezugriff auf die Verbindungsverwaltung.
        """
        assert client.get("/api/nas-connections", headers=api_token_headers).status_code == 403

    def test_api_token_stays_read_only(self, client, api_token_headers):
        response = client.post(
            "/api/nas-connections",
            headers=api_token_headers,
            json={"name": "X", "host": "h", "username": "u", "password": "p"},
        )
        assert response.status_code == 403


# ----------------------------------------------------------------------
# Schema-Migration
# ----------------------------------------------------------------------

class TestMigration:
    def test_existing_database_is_upgraded(self, tmp_path, monkeypatch):
        """Bestandsdatenbank (user_version=0) bekommt die SNMP-Spalten"""
        monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
        reset_key_cache()

        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE nas_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                host TEXT NOT NULL,
                port INTEGER,
                use_https INTEGER NOT NULL DEFAULT 1,
                verify_ssl INTEGER NOT NULL DEFAULT 1,
                username TEXT NOT NULL,
                password_encrypted TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO nas_connections "
            "VALUES (1,'alt','1.2.3.4',5001,1,1,'admin','geheim','2020','2020')"
        )
        conn.commit()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        conn.close()

        from app.services.jobs_store import SCHEMA_VERSION, JobsStore

        store = JobsStore(db_path)

        conn = sqlite3.connect(str(db_path))
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        columns = {row[1] for row in conn.execute("PRAGMA table_info(nas_connections)")}
        assert {"snmp_enabled", "snmp_version", "snmp_port",
                "snmp_secrets_encrypted"} <= columns
        conn.close()

        # Bestandsdaten unverändert, Defaults gesetzt
        connection = store.get_connection(1)
        assert connection["name"] == "alt"
        assert connection["host"] == "1.2.3.4"
        assert connection["snmp_enabled"] is False
        assert store.get_snmp_config(1) is None
        reset_key_cache()

    def test_migration_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
        reset_key_cache()
        from app.services.jobs_store import JobsStore

        db_path = tmp_path / "fresh.db"
        JobsStore(db_path)
        JobsStore(db_path)  # zweiter Lauf darf nicht scheitern
        reset_key_cache()

    def test_snmp_config_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
        reset_key_cache()
        from app.services.jobs_store import JobsStore

        store = JobsStore(tmp_path / "snmp.db")
        created = store.create_connection(
            name="NAS", host="nas.local", username="u", password="p",
            snmp_enabled=True, snmp_version="2c", snmp_port=161,
            snmp_secrets={"community": "geheim"},
        )
        assert "snmp_secrets_encrypted" not in created
        assert created["snmp_enabled"] is True

        config = store.get_snmp_config(created["id"])
        assert config["secrets"]["community"] == "geheim"
        assert config["version"] == "2c"

        # Update ohne neue Zugangsdaten behält die gespeicherten
        store.update_connection(
            created["id"], name="NAS", host="nas.local", username="u",
            snmp_enabled=True, snmp_version="2c", snmp_port=161, snmp_secrets=None,
        )
        assert store.get_snmp_config(created["id"])["secrets"]["community"] == "geheim"
        reset_key_cache()

    def test_secrets_are_encrypted_at_rest(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
        reset_key_cache()
        from app.services.jobs_store import JobsStore

        db_path = tmp_path / "enc.db"
        store = JobsStore(db_path)
        store.create_connection(
            name="NAS", host="nas.local", username="u", password="p",
            snmp_enabled=True, snmp_secrets={"community": "streng-geheim"},
        )
        raw = db_path.read_bytes()
        assert b"streng-geheim" not in raw, "Community darf nicht im Klartext liegen"
        reset_key_cache()
