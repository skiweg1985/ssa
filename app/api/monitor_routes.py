"""Generische Monitoring-Endpoints - werkzeugunabhängig auswertbar.

Vier Berichte, vom Groben ins Feine:
- GET /api/monitor                          -> Gesamtzustand der Instanz
- GET /api/monitor/scans                    -> alle Jobs, mit Roll-up
- GET /api/monitor/scans/{scan_identifier}  -> ein Job
- GET /api/monitor/server                   -> Infrastruktur (Scheduler, System)

Die Auswertung ist für ein Monitoring-System EIN Feldzugriff: `severity`
(0 = OK, 1 = Warnung, 2 = kritisch). Kein Zweit-Call, keine Client-Logik, kein
Parsen von Cron-Ausdrücken. `state` nennt den Grund.

Antworten kommen standardmäßig immer mit HTTP 200 - viele HTTP-Collectoren
verwerfen bei != 2xx den Body und damit genau die Details, die hier stehen.
Der Schweregrad steht zusätzlich in den Headern `X-SSA-Severity` und
`X-SSA-State`; mit `?http_status=1` liefert severity 2 ein HTTP 503, für
Werkzeuge, die nur den Statuscode auswerten können.
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Response

from app.models.monitor import (
    InstanceMonitorReport,
    MonitorSeverity,
    ScanMonitorReport,
    ScansMonitorReport,
    ServerMonitorReport,
)
from app.services.jobs_store import jobs_store
from app.services.monitoring import (
    evaluate_instance,
    evaluate_scan,
    evaluate_scans,
    evaluate_server,
)

logger = logging.getLogger(__name__)

router = APIRouter()

HTTP_STATUS_DESCRIPTION = (
    "1 = Schweregrad zusätzlich als HTTP-Status abbilden (kritisch -> 503)"
)


def _signal(
    response: Response,
    severity: MonitorSeverity,
    state: str,
    http_status: bool,
) -> None:
    """
    Legt Schweregrad-Header und - falls angefordert - den HTTP-Status fest.

    Die Header stehen in JEDER Antwort, damit auch HEAD-Checks und
    header-basierte Alarme ohne Body-Parsing funktionieren.
    """
    response.headers["X-SSA-Severity"] = str(int(severity))
    response.headers["X-SSA-State"] = state
    if http_status and severity >= MonitorSeverity.CRITICAL:
        response.status_code = 503


@router.get(
    "",
    response_model=InstanceMonitorReport,
    summary="Gesamtzustand der Instanz",
)
async def monitor_instance(
    response: Response,
    http_status: bool = Query(False, description=HTTP_STATUS_DESCRIPTION),
) -> InstanceMonitorReport:
    """Ein Check für alles: Maximum aus Server- und Job-Zustand."""
    report = await evaluate_instance()
    _signal(response, report.severity, report.state, http_status)
    return report


@router.get(
    "/scans",
    response_model=ScansMonitorReport,
    summary="Zustand aller Scan-Jobs",
)
async def monitor_scans(
    response: Response,
    include_scans: bool = Query(
        True, description="0 = nur Roll-up und Problemliste, ohne Einzelberichte"
    ),
    http_status: bool = Query(False, description=HTTP_STATUS_DESCRIPTION),
) -> ScansMonitorReport:
    """Roll-up über alle Jobs - `severity` ist das Maximum über alle Jobs."""
    report = evaluate_scans(include_scans=include_scans)
    _signal(response, report.severity, report.state.value, http_status)
    return report


@router.get(
    "/server",
    response_model=ServerMonitorReport,
    summary="Zustand der Infrastruktur",
)
async def monitor_server(
    response: Response,
    http_status: bool = Query(False, description=HTTP_STATUS_DESCRIPTION),
) -> ServerMonitorReport:
    """Scheduler, Systemressourcen, Storage und Konfigurationswarnungen."""
    report = await evaluate_server()
    _signal(response, report.severity, report.state.value, http_status)
    return report


@router.get(
    "/scans/{scan_identifier}",
    response_model=ScanMonitorReport,
    summary="Zustand eines Scan-Jobs",
)
async def monitor_scan(
    scan_identifier: str,
    response: Response,
    http_status: bool = Query(False, description=HTTP_STATUS_DESCRIPTION),
) -> ScanMonitorReport:
    """
    Bericht zu einem Scan-Job (Slug oder Name).

    Ein unbekannter Job ist ein Fehler in der URL, kein überwachter Zustand -
    daher HTTP 404 statt severity 2.
    """
    job = jobs_store.get_job(scan_identifier)
    if job is None:
        raise HTTPException(
            status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden"
        )

    report = evaluate_scan(job)
    _signal(response, report.severity, report.state.value, http_status)
    return report
