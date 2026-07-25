"""SNMP-Abfrage der Synology-Systemmetriken.

Quelle der OIDs ist der offizielle "Synology DiskStation MIB Guide":
https://global.download.synology.com/download/Document/MIBGuide/Synology_MIB_File.zip

SNMP ist der einzige von Synology öffentlich dokumentierte Weg zu Temperatur,
Plattenstatus, RAID-Status und UPS. Die File-Station-HTTP-API liefert davon
nichts, und die HTTP-Endpoints, die es könnten (SYNO.Core.System,
SYNO.Storage.CGI.Storage), sind undokumentiert - deshalb bewusst nicht genutzt.

Voraussetzung am NAS: Systemsteuerung -> Terminal & SNMP -> SNMP aktivieren.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Kurz halten: PRTG bricht den Sensor nach 60 s ab, und zwei Sensoren pro NAS
# teilen sich ohnehin einen Abruf über den Cache in nas_metrics.py.
SNMP_TIMEOUT = 5.0  # Sekunden je Versuch
SNMP_RETRIES = 1

# Synology-Enterprise-OID (MIB Guide, Tabelle 2)
SYNO = "1.3.6.1.4.1.6574"

# Skalare aus der System-MIB (.1) - je mit Instanz-Suffix .0
SYSTEM_OIDS = {
    "system_status": f"{SYNO}.1.1.0",
    "temperature": f"{SYNO}.1.2.0",
    "power_status": f"{SYNO}.1.3.0",
    "system_fan_status": f"{SYNO}.1.4.1.0",
    "cpu_fan_status": f"{SYNO}.1.4.2.0",
    "model_name": f"{SYNO}.1.5.1.0",
    "serial_number": f"{SYNO}.1.5.2.0",
    "dsm_version": f"{SYNO}.1.5.3.0",
    "upgrade_available": f"{SYNO}.1.5.4.0",
}

# Tabellenspalten der Disk-MIB (.2) und RAID-MIB (.3)
DISK_COLUMNS = {
    "name": f"{SYNO}.2.1.1.2",
    "model": f"{SYNO}.2.1.1.3",
    "type": f"{SYNO}.2.1.1.4",
    "status": f"{SYNO}.2.1.1.5",
    "temperature": f"{SYNO}.2.1.1.6",
}
RAID_COLUMNS = {
    "name": f"{SYNO}.3.1.1.2",
    "status": f"{SYNO}.3.1.1.3",
    "free_size": f"{SYNO}.3.1.1.4",
    "total_size": f"{SYNO}.3.1.1.5",
}

# UPS-MIB (.4). Welche Werte ein Gerät liefert, ist geräteabhängig - fehlende
# OIDs sind hier der Normalfall und kein Fehler.
UPS_OIDS = {
    "status": f"{SYNO}.4.2.1.0",
    "load_percent": f"{SYNO}.4.2.12.1.0",
    "battery_charge_percent": f"{SYNO}.4.3.1.1.0",
}

# Standard-MIBs für die echte Auslastung DES NAS (nicht des SSA-Hosts).
UCD_OIDS = {
    "cpu_idle": "1.3.6.1.4.1.2021.11.11.0",
    "mem_total_kb": "1.3.6.1.4.1.2021.4.5.0",
    "mem_avail_kb": "1.3.6.1.4.1.2021.4.6.0",
    "mem_buffer_kb": "1.3.6.1.4.1.2021.4.14.0",
    "mem_cached_kb": "1.3.6.1.4.1.2021.4.15.0",
}
HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"

# Statuswerte sind Enums, keine Messwerte (MIB Guide, Tabellen 5 und 7).
# Sie werden auf Kategorien abgebildet statt roh in PRTG-Limits verdrahtet -
# sonst würde jede neue DSM-Statusnummer den Sensor kippen.
_NORMAL_FAILED = {1: ("ok", "Normal"), 2: ("error", "Failed")}

_DISK_STATUS = {
    1: ("ok", "Normal"),
    2: ("ok", "Initialized"),
    3: ("ok", "NotInitialized"),
    4: ("error", "SystemPartitionFailed"),
    5: ("error", "Crashed"),
}

_RAID_STATUS = {
    1: ("ok", "Normal"),
    2: ("busy", "Repairing"),
    3: ("busy", "Migrating"),
    4: ("busy", "Expanding"),
    5: ("busy", "Deleting"),
    6: ("busy", "Creating"),
    7: ("busy", "RaidSyncing"),
    8: ("busy", "RaidParityChecking"),
    9: ("busy", "RaidAssembling"),
    10: ("busy", "Canceling"),
    11: ("error", "Degrade"),
    12: ("error", "Crashed"),
    13: ("busy", "DataScrubbing"),
    14: ("busy", "RaidDeploying"),
    15: ("busy", "RaidUnDeploying"),
    16: ("busy", "RaidMountCache"),
    17: ("busy", "RaidUnmountCache"),
    18: ("busy", "RaidExpandingUnfinishedSHR"),
    19: ("busy", "RaidConvertSHRToPool"),
    20: ("busy", "RaidMigrateSHR1ToSHR2"),
    21: ("unknown", "RaidUnknownStatus"),
}


class SNMPError(Exception):
    """SNMP-Abfrage fehlgeschlagen (nicht erreichbar, Auth, Timeout)"""


def _map_status(value: Optional[int], table: Dict[int, tuple]) -> tuple:
    """Enum-Wert auf (Kategorie, Klartext) abbilden; Unbekanntes bleibt unknown"""
    if value is None:
        return "unknown", "Unbekannt"
    return table.get(int(value), ("unknown", f"Unbekannt ({value})"))


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _auth_data(config: Dict[str, Any]):
    """Baut die pysnmp-Zugangsdaten für v2c bzw. v3"""
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        UsmUserData,
        usmAesCfb128Protocol,
        usmDESPrivProtocol,
        usmHMACMD5AuthProtocol,
        usmHMACSHAAuthProtocol,
    )

    secrets = config.get("secrets") or {}
    version = str(config.get("version") or "2c")

    if version == "3":
        user = secrets.get("user")
        if not user:
            raise SNMPError("SNMPv3 ist konfiguriert, aber kein Benutzer hinterlegt")
        auth_protocols = {
            "SHA": usmHMACSHAAuthProtocol,
            "MD5": usmHMACMD5AuthProtocol,
        }
        priv_protocols = {
            "AES": usmAesCfb128Protocol,
            "DES": usmDESPrivProtocol,
        }
        return UsmUserData(
            user,
            authKey=secrets.get("auth_key") or None,
            privKey=secrets.get("priv_key") or None,
            authProtocol=auth_protocols.get(secrets.get("auth_protocol") or ""),
            privProtocol=priv_protocols.get(secrets.get("priv_protocol") or ""),
        )

    community = secrets.get("community")
    if not community:
        raise SNMPError("SNMPv2c ist konfiguriert, aber keine Community hinterlegt")
    # mpModel=1 => SNMPv2c
    return CommunityData(community, mpModel=1)


async def _get(engine, auth, target, context, oids: Dict[str, str]) -> Dict[str, Any]:
    """
    Mehrere Skalare in einer Abfrage holen.

    Nicht vorhandene OIDs liefern None statt eines Fehlers: welche Werte ein
    Modell bereitstellt, unterscheidet sich je nach Gerät und DSM-Version.
    """
    from pysnmp.hlapi.v3arch.asyncio import ObjectIdentity, ObjectType, get_cmd

    keys = list(oids.keys())
    var_binds = [ObjectType(ObjectIdentity(oids[key])) for key in keys]

    error_indication, error_status, _, result = await get_cmd(
        engine, auth, target, context, *var_binds
    )
    if error_indication:
        raise SNMPError(str(error_indication))
    if error_status:
        raise SNMPError(str(error_status.prettyPrint()))

    values: Dict[str, Any] = {}
    for key, var_bind in zip(keys, result):
        value = var_bind[1]
        # noSuchObject/noSuchInstance/endOfMibView tragen kein Ergebnis
        if value is None or value.__class__.__name__.startswith("NoSuch"):
            values[key] = None
            continue
        text = value.prettyPrint()
        values[key] = None if text in ("", "No Such Object currently exists at this OID") else text
    return values


async def _walk_column(engine, auth, target, context, base_oid: str) -> Dict[str, Any]:
    """
    Eine Tabellenspalte auslesen. Liefert {Zeilenindex: Wert}.

    Disk- und RAID-Tabelle wachsen und schrumpfen mit der Hardware, deshalb
    Walk statt fester Indizes.
    """
    from pysnmp.hlapi.v3arch.asyncio import (
        ObjectIdentity,
        ObjectType,
        bulk_walk_cmd,
    )

    values: Dict[str, Any] = {}
    async for error_indication, error_status, _, var_binds in bulk_walk_cmd(
        engine,
        auth,
        target,
        context,
        0,
        25,
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    ):
        if error_indication:
            raise SNMPError(str(error_indication))
        if error_status:
            raise SNMPError(str(error_status.prettyPrint()))
        for var_bind in var_binds:
            oid = str(var_bind[0])
            if not oid.startswith(base_oid + "."):
                continue
            index = oid[len(base_oid) + 1:]
            values[index] = var_bind[1].prettyPrint()
    return values


async def _walk_table(
    engine, auth, target, context, columns: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Mehrere Spalten einer Tabelle zu Zeilen zusammenführen"""
    per_column = {}
    for name, oid in columns.items():
        per_column[name] = await _walk_column(engine, auth, target, context, oid)

    indices = sorted(
        {index for column in per_column.values() for index in column},
        key=lambda i: (len(i), i),
    )
    return [
        {name: per_column[name].get(index) for name in columns} for index in indices
    ]


def _build_system(raw: Dict[str, Any], ucd: Dict[str, Any]) -> Dict[str, Any]:
    """Systemwerte aus den Rohantworten zusammensetzen"""
    system_status, system_label = _map_status(
        _as_int(raw.get("system_status")), _NORMAL_FAILED
    )
    power_status, _ = _map_status(_as_int(raw.get("power_status")), _NORMAL_FAILED)
    system_fan, _ = _map_status(
        _as_int(raw.get("system_fan_status")), _NORMAL_FAILED
    )
    cpu_fan, _ = _map_status(_as_int(raw.get("cpu_fan_status")), _NORMAL_FAILED)

    upgrade = _as_int(raw.get("upgrade_available"))
    # 1 = Available; 2-5 heißen "kein Update" bzw. "nicht ermittelbar"
    upgrade_available = None if upgrade is None else upgrade == 1

    cpu_idle = _as_float(ucd.get("cpu_idle"))
    cpu_percent = None if cpu_idle is None else round(max(0.0, 100.0 - cpu_idle), 1)

    mem_total_kb = _as_float(ucd.get("mem_total_kb"))
    mem_avail_kb = _as_float(ucd.get("mem_avail_kb"))
    mem_buffer_kb = _as_float(ucd.get("mem_buffer_kb")) or 0.0
    mem_cached_kb = _as_float(ucd.get("mem_cached_kb")) or 0.0

    memory_total = memory_available = memory_percent = None
    if mem_total_kb and mem_avail_kb is not None:
        # Puffer und Cache zählen als verfügbar - ohne sie meldet Linux
        # dauerhaft ~95 % Belegung und der Wert wäre wertlos.
        available_kb = mem_avail_kb + mem_buffer_kb + mem_cached_kb
        memory_total = int(mem_total_kb * 1024)
        memory_available = int(available_kb * 1024)
        memory_percent = round(
            max(0.0, (mem_total_kb - available_kb) / mem_total_kb * 100), 1
        )

    return {
        "model_name": raw.get("model_name"),
        "dsm_version": raw.get("dsm_version"),
        "system_status": system_status,
        "system_status_label": system_label,
        "power_status": power_status,
        "system_fan_status": system_fan,
        "cpu_fan_status": cpu_fan,
        "temperature_celsius": _as_float(raw.get("temperature")),
        "upgrade_available": upgrade_available,
        "cpu_percent": cpu_percent,
        "memory_total_bytes": memory_total,
        "memory_available_bytes": memory_available,
        "memory_used_percent": memory_percent,
    }


def _build_disks(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    disks = []
    for row in rows:
        status, label = _map_status(_as_int(row.get("status")), _DISK_STATUS)
        disks.append(
            {
                "name": row.get("name") or "unbekannt",
                "model": (row.get("model") or "").strip() or None,
                "status": status,
                "status_label": label,
                "temperature_celsius": _as_float(row.get("temperature")),
            }
        )
    # Stabile Reihenfolge: PRTG identifiziert Kanäle über den Namen
    return sorted(disks, key=lambda d: d["name"])


def _build_raids(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    RAID-Verbünde aus der RAID-MIB.

    ACHTUNG bei used_percent: Die Tabelle enthält Storage Pools UND Volumes,
    ohne Spalte zur Unterscheidung (an einem DS224+/DSM 7.2 verifiziert). Bei
    einem Volume ist freeSize der freie Speicher, bei einem Pool dagegen der
    noch nicht einem Volume zugewiesene Platz - ein vollständig zugewiesener
    Pool meldet also ~100 %, obwohl nichts voll ist.

    Der Wert bleibt hier erhalten (im JSON ist er mit dem Namen einzuordnen),
    taugt aber nicht zum Alarmieren. Dafür ist die Volume-Kapazität aus der
    File-Station-Quelle zuständig.
    """
    raids = []
    for row in rows:
        status, label = _map_status(_as_int(row.get("status")), _RAID_STATUS)
        total = _as_int(row.get("total_size"))
        free = _as_int(row.get("free_size"))
        used_percent = (
            round((total - free) / total * 100, 1)
            if total and free is not None and total > 0
            else None
        )
        raids.append(
            {
                "name": row.get("name") or "unbekannt",
                "status": status,
                "status_label": label,
                "total_bytes": total,
                "free_bytes": free,
                "used_percent": used_percent,
            }
        )
    return sorted(raids, key=lambda r: r["name"])


def _build_ups(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """UPS-Werte, oder None wenn kein Gerät angeschlossen ist"""
    if not any(raw.get(key) for key in ("status", "battery_charge_percent", "load_percent")):
        return None
    return {
        "status": raw.get("status"),
        "battery_charge_percent": _as_float(raw.get("battery_charge_percent")),
        "load_percent": _as_float(raw.get("load_percent")),
    }


async def collect_snmp_health(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Liest die Systemmetriken eines NAS per SNMP.

    Args:
        config: aus jobs_store.get_snmp_config - host, port, version, secrets

    Raises:
        SNMPError: NAS nicht erreichbar, Zugangsdaten falsch, Timeout
    """
    try:
        from pysnmp.hlapi.v3arch.asyncio import (
            ContextData,
            SnmpEngine,
            UdpTransportTarget,
        )
    except ImportError as e:  # pragma: no cover - abhängig von der Installation
        raise SNMPError(
            "pysnmp ist nicht installiert - SNMP-Metriken nicht verfügbar"
        ) from e

    auth = _auth_data(config)
    engine = SnmpEngine()
    context = ContextData()

    try:
        target = await UdpTransportTarget.create(
            (config["host"], int(config.get("port") or 161)),
            timeout=SNMP_TIMEOUT,
            retries=SNMP_RETRIES,
        )

        system_raw = await _get(engine, auth, target, context, SYSTEM_OIDS)
        disk_rows = await _walk_table(engine, auth, target, context, DISK_COLUMNS)
        raid_rows = await _walk_table(engine, auth, target, context, RAID_COLUMNS)

        # Optionale Quellen: fehlen sie, bleibt der Rest trotzdem nutzbar.
        try:
            ucd = await _get(engine, auth, target, context, UCD_OIDS)
        except SNMPError as e:
            logger.debug(f"UCD-Systemwerte nicht verfügbar: {e}")
            ucd = {}
        try:
            ups_raw = await _get(engine, auth, target, context, UPS_OIDS)
        except SNMPError as e:
            logger.debug(f"UPS-Werte nicht verfügbar: {e}")
            ups_raw = {}

        system = _build_system(system_raw, ucd)
        if system["cpu_percent"] is None:
            system["cpu_percent"] = await _hr_processor_load(
                engine, auth, target, context
            )

        return {
            "system": system,
            "disks": _build_disks(disk_rows),
            "raids": _build_raids(raid_rows),
            "ups": _build_ups(ups_raw),
        }
    except SNMPError:
        raise
    except Exception as e:
        raise SNMPError(f"SNMP-Abfrage fehlgeschlagen: {e}") from e
    finally:
        engine.close_dispatcher()


async def _hr_processor_load(engine, auth, target, context) -> Optional[float]:
    """
    CPU-Last als Mittel über hrProcessorLoad.

    Fallback, wenn die UCD-MIB keinen Idle-Wert liefert - das kommt je nach
    DSM-Version vor.
    """
    try:
        loads = await _walk_column(
            engine, auth, target, context, HR_PROCESSOR_LOAD
        )
    except SNMPError as e:
        logger.debug(f"hrProcessorLoad nicht verfügbar: {e}")
        return None

    values = [_as_float(value) for value in loads.values()]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 1)
