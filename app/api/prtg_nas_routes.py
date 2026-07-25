"""PRTG-Sensor-Endpoints für die NAS-Systeme selbst.

Zwei Sensoren je System, bewusst getrennt statt einem Sammelsensor:

- GET /api/prtg/nas/{identifier}/capacity -> Volumes, Freigaben, Belegung
- GET /api/prtg/nas/{identifier}/health   -> Temperatur, Platten, RAID, UPS

Getrennt, weil PRTG maximal 50 Kanäle je Sensor zulässt und beide Bereiche
unterschiedlich alarmiert werden: ein volles Volume ist ein Kapazitätsthema,
eine abgestürzte Platte ein Hardwarethema.

Wie bei den bestehenden Sensoren gilt: immer HTTP 200 (außer bei Auth), und
Probleme gehören als `prtg.error` bzw. über Kanal-Schwellwerte in den
Antwortkörper - siehe app/api/prtg_routes.py.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.models.prtg import PrtgChannel, PrtgResponse, error_response, make_channel, ok_response
from app.services.jobs_store import jobs_store
from app.services.nas_metrics import SNMPNotConfigured, collect_capacity, collect_health

logger = logging.getLogger(__name__)

router = APIRouter()

# PRTG unterstützt maximal 50 Kanäle pro Sensor
MAX_TOTAL_CHANNELS = 50
FIXED_CAPACITY_CHANNELS = 5
CHANNELS_PER_VOLUME = 3
DEFAULT_MAX_VOLUMES = 15
DEFAULT_MAX_DISKS = 24

# Schwellwerte für Belegung. Ab 90 % wird es auf einem NAS eng, ab 95 %
# scheitern Snapshots und Reparaturläufe.
VOLUME_WARN_PERCENT = 85.0
VOLUME_ERR_PERCENT = 95.0

# Temperaturgrenzen: Gehäusewert des NAS bzw. Platten. Platten laufen
# spezifikationsgemäß bis ~60 °C, die Lebensdauer leidet aber deutlich früher.
NAS_TEMP_WARN = 60.0
NAS_TEMP_ERR = 70.0
DISK_TEMP_WARN = 45.0
DISK_TEMP_ERR = 55.0

# Statuskanäle nutzen durchgängig dieselbe Skala, damit ein Schwellwertpaar
# für alle passt: Wartung bleibt grün, Unbekanntes warnt, Fehler ist rot.
STATUS_CODES = {"ok": 0, "busy": 1, "unknown": 2, "error": 3}
STATUS_WARN_MAX = 1.5
STATUS_ERR_MAX = 2.5


def _status_code(status: Optional[str]) -> int:
    return STATUS_CODES.get(status or "unknown", STATUS_CODES["unknown"])


def _status_channel(
    name: str, status: Optional[str], *, with_limits: bool, err_msg: str
) -> PrtgChannel:
    return make_channel(
        name,
        _status_code(status),
        unit="Custom",
        custom_unit="Code",
        warn_max=STATUS_WARN_MAX,
        err_max=STATUS_ERR_MAX,
        warn_msg=f"{name}: Zustand unbekannt",
        err_msg=err_msg,
        with_limits=with_limits,
    )


def _resolve(identifier: str) -> Optional[Dict[str, Any]]:
    return jobs_store.get_connection_by_identifier(identifier)


# ----------------------------------------------------------------------
# Kapazitäts-Sensor
# ----------------------------------------------------------------------

@router.get(
    "/{connection_identifier}/capacity",
    response_model=PrtgResponse,
    response_model_exclude_none=True,
    summary="PRTG-Sensordaten: Kapazität eines NAS",
)
async def prtg_nas_capacity(
    connection_identifier: str,
    volumes: bool = Query(True, description="Einen Kanalsatz je Volume liefern"),
    max_volumes: int = Query(DEFAULT_MAX_VOLUMES, description="Obergrenze für Volume-Kanäle"),
    limits: bool = Query(True, description="Schwellwerte mitliefern (0 = eigene in PRTG pflegen)"),
) -> PrtgResponse:
    """Volumes, Belegung und Freigaben eines NAS als PRTG-Kanäle."""
    try:
        connection = _resolve(connection_identifier)
        if connection is None:
            return error_response(
                f"NAS-Verbindung '{connection_identifier}' nicht gefunden"
            )

        try:
            data, _ = await collect_capacity(connection["id"])
        except Exception as e:
            logger.warning(
                f"PRTG-Kapazität für '{connection_identifier}' fehlgeschlagen: {e}"
            )
            return error_response(
                f"NAS '{connection['name']}' nicht erreichbar - Details siehe Server-Log"
            )

        volume_list: List[Dict[str, Any]] = data.get("volumes", [])
        readonly_count = len([v for v in volume_list if v.get("readonly")])

        channels: List[PrtgChannel] = [
            make_channel("Volumes", len(volume_list), unit="Count"),
            make_channel(
                "Volumes schreibgeschützt",
                readonly_count,
                unit="Count",
                err_max=0.5,
                err_msg=(
                    "Mindestens ein Volume ist schreibgeschützt - "
                    "typisch bei vollem Speicher oder abgestürztem RAID"
                ),
                with_limits=limits,
            ),
            make_channel("Freigaben", data.get("share_count", 0), unit="Count"),
            make_channel(
                "Freigaben ohne Schreibrecht",
                data.get("shares_without_write", 0),
                unit="Count",
            ),
            make_channel(
                "Antwortzeit",
                data.get("response_seconds", 0.0),
                unit="TimeSeconds",
                decimals=2,
            ),
        ]

        # Kanäle je Volume - alphabetisch, damit sie zwischen Läufen stabil
        # bleiben (PRTG identifiziert Kanäle über den Namen).
        truncation_note = ""
        if volumes:
            allowed = max(
                0,
                min(
                    max_volumes,
                    (MAX_TOTAL_CHANNELS - FIXED_CAPACITY_CHANNELS)
                    // CHANNELS_PER_VOLUME,
                ),
            )
            shown = sorted(volume_list, key=lambda v: v["name"])
            if len(shown) > allowed:
                truncation_note = (
                    f" - nur {allowed} von {len(shown)} Volumes als Kanäle "
                    f"(max_volumes={max_volumes})"
                )
                shown = shown[:allowed]
            for volume in shown:
                name = volume["name"]
                channels.extend(
                    [
                        make_channel(
                            f"{name} Belegung",
                            volume.get("used_percent", 0.0),
                            unit="Percent",
                            decimals=1,
                            warn_max=VOLUME_WARN_PERCENT,
                            err_max=VOLUME_ERR_PERCENT,
                            warn_msg=f"{name} füllt sich",
                            err_msg=f"{name} ist nahezu voll",
                            with_limits=limits,
                        ),
                        make_channel(
                            f"{name} frei", volume.get("free_bytes", 0), unit="BytesDisk"
                        ),
                        make_channel(
                            f"{name} gesamt",
                            volume.get("total_bytes", 0),
                            unit="BytesDisk",
                        ),
                    ]
                )

        fullest = max(
            (v.get("used_percent", 0.0) for v in volume_list), default=0.0
        )
        text = (
            f"{len(volume_list)} Volumes, vollstes {fullest:.1f} % | "
            f"{data.get('share_count', 0)} Freigaben{truncation_note}"
        )
        if readonly_count:
            text = f"{readonly_count} Volume(s) schreibgeschützt | " + text
        return ok_response(channels, text=text)

    except Exception:
        # Details nur ins Log: die Antwort erreicht Inhaber eines
        # eingeschränkten Monitoring-Tokens.
        logger.exception(
            f"Fehler beim Erzeugen der PRTG-Kapazitätsdaten für '{connection_identifier}'"
        )
        return error_response(
            "Kapazitätsdaten konnten nicht ausgelesen werden - Details siehe Server-Log"
        )


# ----------------------------------------------------------------------
# Health-Sensor
# ----------------------------------------------------------------------

@router.get(
    "/{connection_identifier}/health",
    response_model=PrtgResponse,
    response_model_exclude_none=True,
    summary="PRTG-Sensordaten: Systemgesundheit eines NAS (SNMP)",
)
async def prtg_nas_health(
    connection_identifier: str,
    disks: bool = Query(False, description="Zusätzlich einen Temperaturkanal je Platte"),
    max_disks: int = Query(DEFAULT_MAX_DISKS, description="Obergrenze für Platten-Kanäle"),
    limits: bool = Query(True, description="Schwellwerte mitliefern (0 = eigene in PRTG pflegen)"),
) -> PrtgResponse:
    """Temperatur, Lüfter, Platten, RAID und UPS eines NAS als PRTG-Kanäle."""
    try:
        connection = _resolve(connection_identifier)
        if connection is None:
            return error_response(
                f"NAS-Verbindung '{connection_identifier}' nicht gefunden"
            )

        try:
            data, _ = await collect_health(connection["id"])
        except SNMPNotConfigured:
            return error_response(
                f"SNMP ist für '{connection['name']}' nicht aktiviert - "
                "Zugang in den NAS-Verbindungen hinterlegen und am NAS unter "
                "Systemsteuerung > Terminal & SNMP freischalten"
            )
        except Exception as e:
            logger.warning(
                f"PRTG-Health für '{connection_identifier}' fehlgeschlagen: {e}"
            )
            return error_response(
                f"SNMP-Abfrage an '{connection['name']}' fehlgeschlagen - "
                "Details siehe Server-Log"
            )

        system: Dict[str, Any] = data.get("system") or {}
        disk_list: List[Dict[str, Any]] = data.get("disks") or []
        raid_list: List[Dict[str, Any]] = data.get("raids") or []
        ups: Optional[Dict[str, Any]] = data.get("ups")

        disks_not_ok = len([d for d in disk_list if d.get("status") != "ok"])
        raids_not_ok = len([r for r in raid_list if r.get("status") == "error"])
        raids_busy = len([r for r in raid_list if r.get("status") == "busy"])
        disk_temps = [
            d["temperature_celsius"]
            for d in disk_list
            if d.get("temperature_celsius") is not None
        ]

        channels: List[PrtgChannel] = [
            _status_channel(
                "Systemstatus",
                system.get("system_status"),
                with_limits=limits,
                err_msg="Systempartition meldet einen Fehler",
            ),
            _status_channel(
                "Netzteil",
                system.get("power_status"),
                with_limits=limits,
                err_msg="Netzteil meldet einen Fehler",
            ),
            _status_channel(
                "Systemlüfter",
                system.get("system_fan_status"),
                with_limits=limits,
                err_msg="Systemlüfter meldet einen Fehler",
            ),
            _status_channel(
                "CPU-Lüfter",
                system.get("cpu_fan_status"),
                with_limits=limits,
                err_msg="CPU-Lüfter meldet einen Fehler",
            ),
            make_channel(
                "DSM-Update verfügbar",
                1 if system.get("upgrade_available") else 0,
                unit="Custom",
                custom_unit="Status",
                warn_max=0.5,
                warn_msg="Für DSM steht ein Update bereit",
                with_limits=limits,
            ),
            make_channel("Platten", len(disk_list), unit="Count"),
            make_channel(
                "Platten nicht normal",
                disks_not_ok,
                unit="Count",
                err_max=0.5,
                err_msg="Mindestens eine Platte meldet einen Fehler",
                with_limits=limits,
            ),
            make_channel("RAID-Verbünde", len(raid_list), unit="Count"),
            make_channel(
                "RAID mit Fehler",
                raids_not_ok,
                unit="Count",
                err_max=0.5,
                err_msg="Mindestens ein RAID ist degraded oder abgestürzt",
                with_limits=limits,
            ),
            make_channel(
                "RAID in Wartung",
                raids_busy,
                unit="Count",
                warn_max=0.5,
                warn_msg="Mindestens ein RAID synchronisiert oder repariert gerade",
                with_limits=limits,
            ),
        ]

        # Messwerte, die nicht jedes Modell liefert, werden weggelassen statt
        # als 0 gemeldet - "0 °C" oder "0 % CPU" liest sich wie ein echter Wert.
        # Gleiche Linie wie beim Server-Sensor ohne psutil.
        optional_channels = (
            (
                "Temperatur",
                system.get("temperature_celsius"),
                {"unit": "Temperature", "decimals": 1,
                 "warn_max": NAS_TEMP_WARN, "err_max": NAS_TEMP_ERR,
                 "warn_msg": "NAS wird warm", "err_msg": "NAS ist zu heiß"},
            ),
            (
                "Höchste Plattentemperatur",
                max(disk_temps) if disk_temps else None,
                {"unit": "Temperature", "decimals": 1,
                 "warn_max": DISK_TEMP_WARN, "err_max": DISK_TEMP_ERR,
                 "warn_msg": "Eine Platte wird warm", "err_msg": "Eine Platte ist zu heiß"},
            ),
            (
                "CPU",
                system.get("cpu_percent"),
                {"unit": "Percent", "decimals": 1, "warn_max": 85, "err_max": 95},
            ),
            (
                "RAM belegt",
                system.get("memory_used_percent"),
                {"unit": "Percent", "decimals": 1, "warn_max": 90, "err_max": 97},
            ),
        )
        missing: List[str] = []
        for name, value, options in optional_channels:
            if value is None:
                missing.append(name)
                continue
            channels.append(make_channel(name, value, with_limits=limits, **options))

        # Belegung je RAID-Verbund (entspricht in DSM dem Volume)
        budget = MAX_TOTAL_CHANNELS - len(channels)
        notes: List[str] = []
        if missing:
            notes.append("ohne " + ", ".join(missing))
        for raid in raid_list:
            if budget <= 0:
                break
            if raid.get("used_percent") is None:
                continue
            channels.append(
                make_channel(
                    f"{raid['name']} Belegung",
                    raid["used_percent"],
                    unit="Percent",
                    decimals=1,
                    warn_max=VOLUME_WARN_PERCENT,
                    err_max=VOLUME_ERR_PERCENT,
                    warn_msg=f"{raid['name']} füllt sich",
                    err_msg=f"{raid['name']} ist nahezu voll",
                    with_limits=limits,
                )
            )
            budget -= 1

        if ups:
            for name, value, unit, extra in (
                ("USV Batterie", ups.get("battery_charge_percent"), "Percent",
                 {"warn_min": 50, "err_min": 25,
                  "warn_msg": "USV-Batterie lädt nicht voll",
                  "err_msg": "USV-Batterie ist fast leer"}),
                ("USV Last", ups.get("load_percent"), "Percent",
                 {"warn_max": 80, "err_max": 95,
                  "warn_msg": "USV ist hoch belastet",
                  "err_msg": "USV ist überlastet"}),
            ):
                if value is None or budget <= 0:
                    continue
                channels.append(
                    make_channel(
                        name, value, unit=unit, decimals=1, with_limits=limits, **extra
                    )
                )
                budget -= 1

        # Temperatur je Platte nur auf Wunsch: die verdichteten Kanäle oben
        # reichen zum Alarmieren, einzeln ist es für die Ursachensuche nützlich.
        if disks:
            allowed = max(0, min(max_disks, budget))
            shown = [d for d in disk_list if d.get("temperature_celsius") is not None]
            if len(shown) > allowed:
                notes.append(
                    f"nur {allowed} von {len(shown)} Platten als Kanäle "
                    f"(max_disks={max_disks})"
                )
                shown = shown[:allowed]
            for disk in shown:
                channels.append(
                    make_channel(
                        f"{disk['name']} Temperatur",
                        disk["temperature_celsius"],
                        unit="Temperature",
                        decimals=1,
                        warn_max=DISK_TEMP_WARN,
                        err_max=DISK_TEMP_ERR,
                        warn_msg=f"{disk['name']} wird warm",
                        err_msg=f"{disk['name']} ist zu heiß",
                        with_limits=limits,
                    )
                )

        model = system.get("model_name") or connection["name"]
        parts = [f"{model}"]
        if system.get("dsm_version"):
            parts.append(str(system["dsm_version"]))
        parts.append(f"{len(disk_list)} Platten")
        if disks_not_ok:
            parts.append(f"{disks_not_ok} mit Fehler")
        if raids_not_ok:
            parts.append(f"{raids_not_ok} RAID mit Fehler")
        elif raids_busy:
            parts.append(f"{raids_busy} RAID in Wartung")
        if ups:
            parts.append("USV angeschlossen")
        if notes:
            parts.append("; ".join(notes))
        return ok_response(channels, text=" | ".join(parts))

    except Exception:
        logger.exception(
            f"Fehler beim Erzeugen der PRTG-Health-Daten für '{connection_identifier}'"
        )
        return error_response(
            "Systemdaten konnten nicht ausgelesen werden - Details siehe Server-Log"
        )
