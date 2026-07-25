"""PRTG-Sensor-Endpoints im "HTTP Data Advanced"-Format.

Zwei Sensoren:
- GET /api/prtg/server                  -> System-, Scheduler- und Storage-Kanäle
- GET /api/prtg/scans/{scan_identifier} -> alle Metriken eines Scan-Jobs

Beide liefern immer HTTP 200 (außer bei Auth-Fehlern): PRTG erwartet Probleme
im Antwortkörper (`prtg.error`) bzw. über Kanal-Schwellwerte, nicht als HTTP-Status.
"""
import asyncio
import logging
from typing import List

from fastapi import APIRouter, Query

from app.models.prtg import PrtgChannel, PrtgResponse, error_response, make_channel, ok_response
from app.services.health import (
    collect_config_warnings,
    collect_job_health,
    collect_scheduler_metrics,
    collect_system_raw,
    format_uptime,
    get_uptime_seconds,
)
from app.services.jobs_store import jobs_store
from app.services.monitoring import (
    age_limits,
    age_seconds,
    as_utc,
    expected_path_count,
    folder_balance,
)
from app.services.scanner import scanner_service
from app.services.scheduler import scheduler_service
from app.services.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter()

# PRTG unterstützt maximal 50 Kanäle pro Sensor
MAX_TOTAL_CHANNELS = 50
FIXED_JOB_CHANNELS = 9
DEFAULT_MAX_FOLDERS = 40

# Status-Codes des "Status"-Kanals (aufsteigend nach Schwere,
# damit ein einzelnes Max-Limit Warning und Error abdeckt)
STATUS_OK = 0          # letzter Lauf erfolgreich
STATUS_RUNNING = 1     # Scan läuft gerade
STATUS_DISABLED = 2    # Job deaktiviert
STATUS_STALE = 3       # eingeplant, aber kein aktueller Lauf -> Warning
STATUS_FAILED = 4      # letzter Lauf fehlgeschlagen -> Error


# Zeit-, Pfad- und Schwellwert-Helfer stehen in app/services/monitoring.py,
# damit PRTG- und generische Monitoring-Endpoints dieselben Werte berechnen.


# ----------------------------------------------------------------------
# Job-Sensor
# ----------------------------------------------------------------------

@router.get(
    "/scans/{scan_identifier}",
    response_model=PrtgResponse,
    response_model_exclude_none=True,
    summary="PRTG-Sensordaten für einen Scan-Job",
)
async def prtg_scan(
    scan_identifier: str,
    folders: bool = Query(True, description="Einen Kanal je gescanntem Ordner liefern"),
    max_folders: int = Query(DEFAULT_MAX_FOLDERS, description="Obergrenze für Ordner-Kanäle"),
    limits: bool = Query(True, description="Schwellwerte mitliefern (0 = eigene in PRTG pflegen)"),
) -> PrtgResponse:
    """Liefert alle Metriken eines Scan-Jobs als PRTG-Kanäle."""
    try:
        job = jobs_store.get_job(scan_identifier)
        if job is None:
            return error_response(f"Scan '{scan_identifier}' nicht gefunden")

        slug = job["slug"]
        latest = storage.get_latest_result(slug)
        latest_completed = storage.get_latest_completed_result(slug)
        is_running = scanner_service.is_scan_running(slug)

        if latest is None:
            return error_response(
                f"Noch keine Scan-Ergebnisse für '{job['name']}' - "
                "Sensor bitte nach dem ersten Lauf anlegen"
            )
        if latest_completed is None:
            detail = f": {latest.error}" if latest.error else ""
            return error_response(
                f"Noch kein erfolgreicher Lauf für '{job['name']}'{detail}"
            )

        # Messwerte kommen aus dem letzten ERFOLGREICHEN Lauf, damit ein
        # fehlgeschlagener Lauf keinen 0-Einbruch in den PRTG-Charts erzeugt.
        successful = [item for item in latest_completed.results if item.success]
        total_bytes = sum(
            item.total_size.bytes for item in successful if item.total_size
        )
        total_dirs = sum(item.num_dir or 0 for item in successful)
        total_files = sum(item.num_file or 0 for item in successful)
        duration_seconds = (
            sum(item.elapsed_time_ms or 0 for item in successful) / 1000.0
        )

        # Ordnerbilanz über den geteilten Helfer: nur erfolgreiche Ordner werden
        # persistiert, deshalb der Abgleich mit der konfigurierten Pfadanzahl -
        # der aber ausgesetzt wird, wenn die Konfiguration nach dem Lauf
        # geändert wurde (neu hinzugefügte Pfade sind keine Fehler).
        _, failed_folders, _ = folder_balance(
            job, latest_completed, expected_path_count(job)
        )

        # Status ermitteln
        if is_running:
            status_code = STATUS_RUNNING
            status_text = "Scan läuft"
        elif not job["enabled"]:
            status_code = STATUS_DISABLED
            status_text = "Job deaktiviert"
        elif latest.status == "failed":
            status_code = STATUS_FAILED
            status_text = f"Letzter Lauf fehlgeschlagen: {latest.error or 'unbekannt'}"
        elif scheduler_service.get_job_info(slug) is None:
            status_code = STATUS_STALE
            status_text = "Job ist nicht eingeplant"
        else:
            status_code = STATUS_OK
            status_text = "OK"

        # Alters-Limits nur wenn der Job aktiv eingeplant ist - ein bewusst
        # deaktivierter Job würde sonst zwangsläufig rot.
        interval_seconds = (
            scheduler_service.get_expected_interval_seconds(slug)
            if job["enabled"]
            else None
        )
        run_limits = age_limits(interval_seconds, 2, 3)
        data_limits = age_limits(interval_seconds, 3, 5)

        channels: List[PrtgChannel] = [
            make_channel("Gesamtgröße", total_bytes, unit="BytesDisk"),
            make_channel("Ordner", total_dirs, unit="Count"),
            make_channel("Dateien", total_files, unit="Count"),
            make_channel(
                "Scan-Dauer", duration_seconds, unit="TimeSeconds", decimals=1
            ),
            make_channel(
                "Alter letzter Lauf",
                age_seconds(latest.timestamp),
                unit="TimeSeconds",
                warn_max=run_limits["warn_max"],
                err_max=run_limits["err_max"],
                warn_msg="Scan länger nicht gelaufen als erwartet",
                err_msg="Scan ist deutlich überfällig",
                with_limits=limits,
            ),
            make_channel(
                "Alter letzte Daten",
                age_seconds(latest_completed.timestamp),
                unit="TimeSeconds",
                warn_max=data_limits["warn_max"],
                err_max=data_limits["err_max"],
                warn_msg="Letzte erfolgreiche Daten werden alt",
                err_msg="Seit langem kein erfolgreicher Scan mehr",
                with_limits=limits,
            ),
            make_channel(
                "Status",
                status_code,
                unit="Custom",
                custom_unit="Code",
                warn_max=2.5,
                err_max=3.5,
                warn_msg="Job ist nicht eingeplant",
                err_msg="Letzter Scan-Lauf fehlgeschlagen",
                with_limits=limits,
            ),
            make_channel("Ordner OK", len(successful), unit="Count"),
            make_channel(
                "Ordner Fehler",
                failed_folders,
                unit="Count",
                err_max=0.5,
                err_msg="Mindestens ein Ordner konnte nicht gescannt werden",
                with_limits=limits,
            ),
        ]

        # Ein Kanal je Ordner - alphabetisch, damit die Kanäle zwischen Läufen
        # stabil bleiben (PRTG identifiziert Kanäle über den Namen).
        truncation_note = ""
        if folders:
            folder_items = sorted(
                (item for item in successful if item.total_size),
                key=lambda item: item.folder_name,
            )
            allowed = max(0, min(max_folders, MAX_TOTAL_CHANNELS - FIXED_JOB_CHANNELS))
            if len(folder_items) > allowed:
                truncation_note = (
                    f" - nur {allowed} von {len(folder_items)} Ordnern als Kanäle "
                    f"(max_folders={max_folders})"
                )
                folder_items = folder_items[:allowed]
            for item in folder_items:
                channels.append(
                    make_channel(
                        item.folder_name, item.total_size.bytes, unit="BytesDisk"
                    )
                )

        last_run = as_utc(latest.timestamp).strftime("%d.%m.%Y %H:%M UTC")
        text = (
            f"{status_text} | Letzter Lauf {last_run} | "
            f"{len(successful)} Ordner OK{truncation_note}"
        )
        return ok_response(channels, text=text)

    except Exception:
        # Details nur ins Log - die Antwort erreicht Inhaber eines eingeschränkten
        # Monitoring-Tokens und soll keine internen Fehlertexte preisgeben.
        logger.exception(f"Fehler beim Erzeugen der PRTG-Daten für '{scan_identifier}'")
        return error_response(
            "Scan-Daten konnten nicht ausgelesen werden - Details siehe Server-Log"
        )


# ----------------------------------------------------------------------
# Server-Sensor
# ----------------------------------------------------------------------

@router.get(
    "/server",
    response_model=PrtgResponse,
    response_model_exclude_none=True,
    summary="PRTG-Sensordaten für den Server selbst",
)
async def prtg_server(
    limits: bool = Query(True, description="Schwellwerte mitliefern"),
) -> PrtgResponse:
    """Liefert System-, Scheduler- und Storage-Metriken als PRTG-Kanäle."""
    try:
        channels: List[PrtgChannel] = []
        notes: List[str] = []

        uptime = get_uptime_seconds()
        channels.append(make_channel("Uptime", uptime or 0, unit="TimeSeconds"))

        # Systemressourcen nur wenn psutil verfügbar ist. Fehlende Kanäle sind
        # besser als 0-Werte, die als "0 % CPU" fehlgedeutet würden.
        # In einem Thread, weil psutil.cpu_percent bewusst 100 ms blockiert.
        system = await asyncio.to_thread(collect_system_raw)
        if system is not None:
            channels.extend(
                [
                    make_channel(
                        "CPU",
                        system["cpu_percent"],
                        unit="Percent",
                        decimals=1,
                        warn_max=85,
                        err_max=95,
                        with_limits=limits,
                    ),
                    make_channel(
                        "RAM belegt",
                        system["mem_percent"],
                        unit="Percent",
                        decimals=1,
                        warn_max=85,
                        err_max=95,
                        with_limits=limits,
                    ),
                    make_channel("RAM frei", system["mem_available"], unit="BytesMemory"),
                    make_channel(
                        "Disk belegt",
                        system["disk_percent"],
                        unit="Percent",
                        decimals=1,
                        warn_max=85,
                        err_max=95,
                        with_limits=limits,
                    ),
                    make_channel("Disk frei", system["disk_free"], unit="BytesDisk"),
                ]
            )
        else:
            notes.append("psutil nicht verfügbar - keine Systemwerte")

        scheduler_metrics = collect_scheduler_metrics()
        scheduler_running = 1 if scheduler_metrics.get("running") else 0
        channels.append(
            make_channel(
                "Scheduler",
                scheduler_running,
                unit="Custom",
                custom_unit="Status",
                err_min=0.5,
                err_msg="Scheduler läuft nicht - es werden keine Scans ausgeführt",
                with_limits=limits,
            )
        )

        jobs = collect_job_health()
        channels.extend(
            [
                make_channel("Jobs gesamt", jobs["total"], unit="Count"),
                make_channel("Jobs aktiv", jobs["enabled"], unit="Count"),
                make_channel("Scans laufend", jobs["running"], unit="Count"),
                make_channel(
                    "Jobs mit Fehler",
                    jobs["failed"],
                    unit="Count",
                    err_max=0.5,
                    err_msg="Mindestens ein Job ist beim letzten Lauf fehlgeschlagen",
                    with_limits=limits,
                ),
                make_channel(
                    "Jobs ohne Ergebnisse",
                    jobs["without_results"],
                    unit="Count",
                    warn_max=0.5,
                    warn_msg="Mindestens ein Job hat noch nie Ergebnisse geliefert",
                    with_limits=limits,
                ),
                make_channel(
                    "Ältester Lauf", jobs["stalest_seconds"] or 0, unit="TimeSeconds"
                ),
            ]
        )

        storage_stats = storage.get_storage_stats()
        channels.extend(
            [
                make_channel(
                    "DB-Größe", storage_stats.get("db_size_bytes", 0), unit="BytesFile"
                ),
                make_channel(
                    "Ergebnisse in DB",
                    storage_stats.get("total_results_db", 0),
                    unit="Count",
                ),
            ]
        )

        warnings = collect_config_warnings()
        channels.append(
            make_channel(
                "Konfigurationswarnungen",
                len(warnings),
                unit="Count",
                warn_max=0.5,
                warn_msg="Die Konfiguration enthält Warnungen",
                with_limits=limits,
            )
        )

        summary = (
            f"{jobs['total']} Jobs, {jobs['running']} laufend, "
            f"{jobs['failed']} mit Fehler"
        )
        if uptime is not None:
            summary += f", Uptime {format_uptime(uptime)}"
        if notes:
            summary += " (" + "; ".join(notes) + ")"

        return ok_response(channels, text=summary)

    except Exception:
        logger.exception("Fehler beim Erzeugen der PRTG-Serverdaten")
        return error_response(
            "Serverdaten konnten nicht ausgelesen werden - Details siehe Server-Log"
        )
