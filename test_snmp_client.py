"""Tests für die SNMP-Auswertung (app/services/snmp_client.py).

Getestet wird die Aufbereitung der Rohantworten, nicht das Netzwerk: die
OID-Werte kommen von pysnmp durchgängig als Strings, deshalb geben alle
Fixtures hier ebenfalls Strings vor.

Referenz für Statuswerte und OIDs: Synology DiskStation MIB Guide.
"""
import pytest

from app.services.snmp_client import (
    DISK_COLUMNS,
    RAID_COLUMNS,
    SYNO,
    SYSTEM_OIDS,
    SNMPError,
    _DISK_STATUS,
    _RAID_STATUS,
    _auth_data,
    _build_disks,
    _build_raids,
    _build_system,
    _build_ups,
    _map_status,
)


class TestOIDs:
    def test_enterprise_base(self):
        """Synology-Enterprise-OID laut MIB Guide, Tabelle 2"""
        assert SYNO == "1.3.6.1.4.1.6574"

    def test_system_oids_are_scalars(self):
        """Skalare brauchen das Instanz-Suffix .0, sonst liefert SNMP nichts"""
        for name, oid in SYSTEM_OIDS.items():
            assert oid.startswith(f"{SYNO}.1."), name
            assert oid.endswith(".0"), f"{name} ist kein Skalar-OID"

    def test_table_columns_have_no_instance_suffix(self):
        """Tabellenspalten werden gewalkt - ein .0 wäre hier falsch"""
        for columns, mib in ((DISK_COLUMNS, "2"), (RAID_COLUMNS, "3")):
            for name, oid in columns.items():
                assert oid.startswith(f"{SYNO}.{mib}.1.1."), name
                assert not oid.endswith(".0"), name


class TestStatusMapping:
    def test_raid_degrade_and_crashed_are_errors(self):
        """Degrade(11) und Crashed(12) sind die Zustände, die alarmieren müssen"""
        assert _map_status(11, _RAID_STATUS) == ("error", "Degrade")
        assert _map_status(12, _RAID_STATUS) == ("error", "Crashed")

    def test_raid_maintenance_is_not_an_error(self):
        """Resync/Repair/Expand sind Wartung - kein Grund für einen Alarm"""
        for value in (2, 3, 4, 7, 8, 13):
            category, _ = _map_status(value, _RAID_STATUS)
            assert category == "busy", f"RAID-Status {value} darf nicht 'error' sein"

    def test_raid_normal(self):
        assert _map_status(1, _RAID_STATUS) == ("ok", "Normal")

    def test_disk_status_mapping(self):
        assert _map_status(1, _DISK_STATUS)[0] == "ok"
        assert _map_status(3, _DISK_STATUS)[0] == "ok"   # NotInitialized: leere Platte
        assert _map_status(4, _DISK_STATUS)[0] == "error"
        assert _map_status(5, _DISK_STATUS)[0] == "error"

    def test_unknown_status_stays_unknown(self):
        """
        Neue DSM-Statusnummern dürfen den Sensor nicht rot färben.

        Deshalb wird auf Kategorien abgebildet statt Rohzahlen in PRTG-Limits
        zu verdrahten.
        """
        category, label = _map_status(99, _RAID_STATUS)
        assert category == "unknown"
        assert "99" in label

    def test_missing_value_is_unknown(self):
        assert _map_status(None, _DISK_STATUS) == ("unknown", "Unbekannt")


class TestBuildSystem:
    def test_full_reading(self):
        system = _build_system(
            {
                "system_status": "1", "temperature": "42", "power_status": "1",
                "system_fan_status": "1", "cpu_fan_status": "2",
                "model_name": "DS920+", "dsm_version": "DSM 7.2",
                "upgrade_available": "1",
            },
            {
                "cpu_idle": "87.5", "mem_total_kb": "8000000",
                "mem_avail_kb": "400000", "mem_buffer_kb": "100000",
                "mem_cached_kb": "3000000",
            },
        )
        assert system["system_status"] == "ok"
        assert system["cpu_fan_status"] == "error"
        assert system["temperature_celsius"] == 42.0
        assert system["upgrade_available"] is True
        assert system["cpu_percent"] == 12.5

    def test_memory_counts_buffer_and_cache_as_available(self):
        """
        Ohne Puffer und Cache meldet Linux dauerhaft ~95 % Belegung.

        Der Wert wäre dann konstant rot und damit wertlos.
        """
        system = _build_system(
            {},
            {
                "mem_total_kb": "1000", "mem_avail_kb": "100",
                "mem_buffer_kb": "200", "mem_cached_kb": "300",
            },
        )
        # verfügbar = 100 + 200 + 300 = 600 von 1000
        assert system["memory_used_percent"] == 40.0
        assert system["memory_available_bytes"] == 600 * 1024

    def test_upgrade_states_other_than_available(self):
        """Nur Available(1) heißt "Update da"; 2-5 heißen es nicht"""
        for value in ("2", "3", "4", "5"):
            assert _build_system({"upgrade_available": value}, {})[
                "upgrade_available"] is False

    def test_missing_values_stay_none(self):
        """Was das Modell nicht liefert, darf nicht als 0 erfunden werden"""
        system = _build_system({}, {})
        assert system["temperature_celsius"] is None
        assert system["cpu_percent"] is None
        assert system["memory_used_percent"] is None
        assert system["system_status"] == "unknown"

    def test_non_numeric_values_are_tolerated(self):
        system = _build_system({"temperature": "n/a"}, {"cpu_idle": ""})
        assert system["temperature_celsius"] is None
        assert system["cpu_percent"] is None


class TestBuildDisks:
    def test_sorted_by_name_for_stable_prtg_channels(self):
        disks = _build_disks(
            [
                {"name": "Drive 2", "model": "WD40", "status": "1", "temperature": "40"},
                {"name": "Drive 1", "model": "ST4000", "status": "1", "temperature": "38"},
            ]
        )
        assert [d["name"] for d in disks] == ["Drive 1", "Drive 2"]

    def test_crashed_disk(self):
        disk = _build_disks(
            [{"name": "Drive 3", "model": " X ", "status": "5", "temperature": "58"}]
        )[0]
        assert disk["status"] == "error"
        assert disk["status_label"] == "Crashed"
        assert disk["temperature_celsius"] == 58.0
        assert disk["model"] == "X"

    def test_empty_table(self):
        assert _build_disks([]) == []


class TestBuildRaids:
    def test_used_percent(self):
        raid = _build_raids(
            [{"name": "Volume 1", "status": "1",
              "total_size": "1000", "free_size": "250"}]
        )[0]
        assert raid["used_percent"] == 75.0

    def test_missing_sizes_stay_none(self):
        raid = _build_raids([{"name": "Volume 1", "status": "1"}])[0]
        assert raid["used_percent"] is None
        assert raid["total_bytes"] is None

    def test_zero_total_does_not_divide_by_zero(self):
        raid = _build_raids(
            [{"name": "V", "status": "1", "total_size": "0", "free_size": "0"}]
        )[0]
        assert raid["used_percent"] is None


class TestBuildUps:
    def test_no_ups_connected(self):
        assert _build_ups({}) is None
        assert _build_ups({"status": None, "load_percent": None}) is None

    def test_ups_present(self):
        ups = _build_ups(
            {"status": "OL", "battery_charge_percent": "100", "load_percent": "23.5"}
        )
        assert ups["status"] == "OL"
        assert ups["battery_charge_percent"] == 100.0
        assert ups["load_percent"] == 23.5


class TestAuthData:
    def test_v2c_requires_community(self):
        with pytest.raises(SNMPError, match="Community"):
            _auth_data({"version": "2c", "secrets": {}})

    def test_v3_requires_user(self):
        with pytest.raises(SNMPError, match="Benutzer"):
            _auth_data({"version": "3", "secrets": {}})

    def test_v2c_builds_community_data(self):
        auth = _auth_data({"version": "2c", "secrets": {"community": "public"}})
        assert auth.__class__.__name__ == "CommunityData"

    def test_v3_builds_usm_user_data(self):
        auth = _auth_data(
            {
                "version": "3",
                "secrets": {
                    "user": "monitor", "auth_protocol": "SHA", "auth_key": "authpass123",
                    "priv_protocol": "AES", "priv_key": "privpass123",
                },
            }
        )
        assert auth.__class__.__name__ == "UsmUserData"

    def test_default_version_is_v2c(self):
        """v2c ist in Bestandsumgebungen der verbreitete Standard"""
        auth = _auth_data({"secrets": {"community": "public"}})
        assert auth.__class__.__name__ == "CommunityData"
