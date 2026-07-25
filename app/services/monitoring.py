"""Gemeinsame Auswertungslogik für alle Monitoring-Endpoints.

Einzige Quelle der Wahrheit für "wie geht es diesem Scan-Job?". Genutzt von:
- app/api/prtg_routes.py    -> PRTG-Sensoren ("HTTP Data Advanced")
- app/api/monitor_routes.py -> generische Monitoring-Endpoints

Die Zeit-/Pfad-Helfer lagen ursprünglich in prtg_routes.py. Sie stehen hier,
damit beide Endpoint-Familien dieselben Schwellwerte und dieselbe
Ordner-Fehler-Formel verwenden - "überfällig" muss in PRTG und im generischen
Bericht denselben Zeitpunkt bedeuten.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.monitor import (
    SEVERITY_BY_SERVER_STATE,
    SEVERITY_BY_STATE,
    ComponentRef,
    InstanceMonitorReport,
    JobsInfo,
    LastRunInfo,
    LastSuccessInfo,
    MonitorSeverity,
    MonitorState,
    ProblemRef,
    RunInfo,
    ScanMonitorReport,
    ScanRef,
    ScansMonitorReport,
    ScansSummary,
    ScheduleInfo,
    SchedulerInfo,
    ServerInfo,
    ServerMonitorReport,
    ServerState,
    StorageInfo,
    SystemInfo,
    severity_text,
)

logger = logging.getLogger(__name__)

# Untergrenze der Hängen-Schwelle: ein Job mit einem einzigen Pfad soll nicht
# schon nach zehn Minuten als hängend gelten.
MIN_STUCK_AFTER_SECONDS = 1800

# Auswertungsreihenfolge der Gründe: der erste zutreffende bestimmt `state`.
# Bewusst NICHT nach Severity sortiert - DISABLED hat Severity 0, muss aber
# jeden Fehlergrund überstimmen: ein absichtlich deaktivierter Job darf nicht
# alarmieren, auch wenn sein letzter Lauf fehlgeschlagen ist.
STATE_PRECEDENCE: Tuple[MonitorState, ...] = (
    MonitorState.ERROR,
    MonitorState.DISABLED,
    # STUCK vor FAILED: der Zustand ist akut und blockiert den Job gerade,
    # während FAILED einen bereits beendeten Lauf beschreibt.
    MonitorState.STUCK,
    MonitorState.FAILED,
    MonitorState.OVERDUE,
    MonitorState.NEVER_RUN,
    MonitorState.UNSCHEDULED,
    MonitorState.CANCELLED,
    MonitorState.STALE,
    MonitorState.PARTIAL,
    MonitorState.OK,  # Schlusslicht: gilt, wenn kein anderer Grund zutrifft
)


def state_precedence(state: MonitorState) -> int:
    """Position eines States in der Auswertungsreihenfolge (kleiner = wichtiger)"""
    try:
        return STATE_PRECEDENCE.index(state)
    except ValueError:  # pragma: no cover - schützt vor neuen States ohne Eintrag
        return len(STATE_PRECEDENCE)


# ----------------------------------------------------------------------
# Zeit-Helfer
# ----------------------------------------------------------------------

def as_utc(value: datetime) -> datetime:
    """
    Stellt sicher, dass ein Timestamp tz-bewusst ist.

    Ältere Datensätze können naive Timestamps enthalten (der Scanner nutzte im
    Fehlerpfad datetime.utcnow()). Ohne diese Normalisierung würde die
    Altersberechnung mit TypeError abbrechen.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def age_seconds(timestamp: Optional[datetime]) -> Optional[float]:
    """Alter eines Timestamps in Sekunden, None wenn kein Timestamp vorliegt"""
    if timestamp is None:
        return None
    return (datetime.now(timezone.utc) - as_utc(timestamp)).total_seconds()


# ----------------------------------------------------------------------
# Pfad- und Schwellwert-Helfer
# ----------------------------------------------------------------------

def expected_path_count(job: Dict[str, Any]) -> int:
    """
    Anzahl der Pfade, die dieser Job scannen soll.

    Nötig, weil nur erfolgreiche Ordner persistiert werden: nach einem Neustart
    wäre "Ordner Fehler" sonst fälschlich 0.
    """
    try:
        from app.api.routes import _job_to_view_config
        from app.services.scanner import scanner_service

        config = _job_to_view_config(job)
        if config is None:
            return 0
        return len(scanner_service._determine_paths(config))
    except Exception as e:
        logger.debug(f"Erwartete Pfadanzahl nicht ermittelbar: {e}")
        return 0


def age_limits(
    interval_seconds: Optional[float], warn_factor: float, err_factor: float
) -> Dict[str, Optional[float]]:
    """
    Schwellwerte für die Alters-Kanäle aus dem Scan-Intervall.

    Untergrenze verhindert, dass Minuten-Jobs bei jedem kleinen Verzug flattern.
    """
    if interval_seconds is None or interval_seconds <= 0:
        return {"warn_max": None, "err_max": None}
    return {
        "warn_max": max(interval_seconds * warn_factor, interval_seconds + 300),
        "err_max": max(interval_seconds * err_factor, interval_seconds + 600),
    }


def stuck_after_seconds(path_count: int) -> float:
    """
    Ab welcher Laufzeit ein Scan als hängend gilt.

    Abgeleitet aus der Pfadanzahl statt aus dem Scan-Intervall: der Scanner
    räumt jedem Pfad ein Timeout von PATH_MAX_WAIT_SECONDS ein, damit ist die
    plausible Obergrenze eines Laufs berechenbar - auch für Jobs, deren
    Intervall sich nicht ermitteln lässt. Verdoppelt als Puffer (Login, Logout,
    Wiederholungen), mit einer Untergrenze, damit kleine Jobs nicht bei jeder
    Verzögerung als hängend gelten.
    """
    from app.services.scanner import PATH_MAX_WAIT_SECONDS

    return max(
        MIN_STUCK_AFTER_SECONDS, max(1, path_count) * PATH_MAX_WAIT_SECONDS * 2
    )


def compute_progress_percent(
    progress: Dict[str, Any], last_completed: Optional[Any]
) -> Optional[float]:
    """
    Fortschritt eines laufenden Scans in Prozent, gemessen am letzten
    erfolgreichen Lauf.

    Gewichtet pro Ordner nach dessen historischer Größe und mischt die
    Metriken (Größe 70 %, Ordner 20 %, Dateien 10 %). Ohne historischen
    Vergleichslauf ist keine Aussage möglich - dann None.

    Genutzt von GET /api/scans/{slug}/progress und den Monitoring-Berichten,
    damit Oberfläche und Monitoring dieselbe Zahl zeigen.
    """
    if not last_completed or not last_completed.results:
        return None

    path_status = progress.get("path_status", {})

    def normalize(p: str) -> str:
        return p.strip().strip("/")

    # Historische Werte je Pfad
    historical_by_path: Dict[str, Dict[str, int]] = {}
    for item in last_completed.results:
        if item.success:
            historical_by_path[normalize(item.folder_name)] = {
                "size": item.total_size.bytes if item.total_size else 0,
                "dirs": item.num_dir or 0,
                "files": item.num_file or 0,
            }

    # Aktuelle Werte je Pfad; bei Kollision gewinnt der weiter fortgeschrittene
    normalized_path_status: Dict[str, Dict[str, Any]] = {}
    for path, status in path_status.items():
        key = normalize(path)
        existing = normalized_path_status.get(key)
        if existing is None or status.get("total_size", 0) > existing.get("total_size", 0):
            normalized_path_status[key] = status

    weighted_size = weighted_dirs = weighted_files = 0.0
    total_weight = 0.0

    for key, historical in historical_by_path.items():
        current = normalized_path_status.get(key, {})
        current_size = current.get("total_size", 0) or 0
        current_dirs = current.get("num_dir", 0) or 0
        current_files = current.get("num_file", 0) or 0
        finished = bool(current.get("finished", False))

        hist_size = historical["size"]
        hist_dirs = historical["dirs"]
        hist_files = historical["files"]

        # Gewicht: die Größe ist der genaueste Indikator, sonst Ordner/Dateien
        if hist_size > 0:
            weight = float(hist_size)
        elif hist_dirs > 0:
            weight = hist_dirs * 1000.0
        elif hist_files > 0:
            weight = float(hist_files)
        else:
            weight = 1.0

        def ratio(current_value: int, historical_value: int) -> float:
            if historical_value > 0:
                return min(100.0, max(0.0, (current_value / historical_value) * 100))
            # Leerer Ordner: erst mit dem finished-Flag zu 100 %
            return 100.0 if finished else 0.0

        weighted_size += ratio(current_size, hist_size) * weight
        weighted_dirs += ratio(current_dirs, hist_dirs) * weight
        weighted_files += ratio(current_files, hist_files) * weight
        total_weight += weight

    if total_weight > 0:
        size_percent = weighted_size / total_weight
        dirs_percent = weighted_dirs / total_weight
        files_percent = weighted_files / total_weight
    else:
        # Greift nur, wenn KEIN historischer Pfad Gewicht hat - also praktisch
        # nur, wenn der Vergleichslauf keine erfolgreichen Ordner enthält.
        # Ein leerer path_status allein führt NICHT hierher, sondern oben zu 0 %.
        historical_total_size = sum(
            item.total_size.bytes
            for item in last_completed.results
            if item.success and item.total_size and item.total_size.bytes > 0
        )
        historical_total_dirs = sum(
            item.num_dir or 0 for item in last_completed.results if item.success
        )
        historical_total_files = sum(
            item.num_file or 0 for item in last_completed.results if item.success
        )

        def total_ratio(current_value: int, historical_value: int) -> float:
            if historical_value > 0:
                return min(100.0, max(0.0, (current_value / historical_value) * 100))
            return 0.0

        size_percent = total_ratio(progress.get("total_size", 0) or 0, historical_total_size)
        dirs_percent = total_ratio(progress.get("num_dir", 0) or 0, historical_total_dirs)
        files_percent = total_ratio(progress.get("num_file", 0) or 0, historical_total_files)

    return round(size_percent * 0.7 + dirs_percent * 0.2 + files_percent * 0.1, 1)


def format_age(seconds: Optional[float]) -> str:
    """Alter als deutscher Text ("vor 12 Minuten") für das `message`-Feld"""
    if seconds is None:
        return "unbekannt"
    seconds = max(0.0, seconds)
    if seconds < 10:
        return "gerade eben"
    if seconds < 90:
        return f"vor {int(seconds)} Sekunden"
    minutes = seconds / 60
    if minutes < 90:
        value = int(round(minutes))
        return f"vor {value} Minute{'n' if value != 1 else ''}"
    hours = seconds / 3600
    if hours < 48:
        value = int(round(hours))
        return f"vor {value} Stunde{'n' if value != 1 else ''}"
    value = int(round(seconds / 86400))
    return f"vor {value} Tag{'en' if value != 1 else ''}"


def format_duration(seconds: Optional[float]) -> str:
    """Dauer als deutscher Text ("2 Stunden") - für Laufzeiten, nicht für Alter"""
    if seconds is None:
        return "unbekannt"
    seconds = max(0.0, seconds)
    if seconds < 90:
        return f"{int(seconds)} Sekunden"
    minutes = seconds / 60
    if minutes < 90:
        value = int(round(minutes))
        return f"{value} Minute{'n' if value != 1 else ''}"
    hours = seconds / 3600
    if hours < 48:
        value = int(round(hours))
        return f"{value} Stunde{'n' if value != 1 else ''}"
    value = int(round(seconds / 86400))
    return f"{value} Tag{'en' if value != 1 else ''}"


def format_interval(seconds: Optional[float]) -> str:
    """Intervall als deutscher Text ("alle 6 Stunden")"""
    if seconds is None or seconds <= 0:
        return "unbekannt"
    if seconds < 90:
        return f"alle {int(seconds)} Sekunden"
    minutes = seconds / 60
    if minutes < 90:
        value = int(round(minutes))
        return f"alle {value} Minute{'n' if value != 1 else ''}"
    hours = seconds / 3600
    if hours < 48:
        value = int(round(hours))
        return f"alle {value} Stunde{'n' if value != 1 else ''}"
    value = int(round(seconds / 86400))
    return f"alle {value} Tag{'e' if value != 1 else ''}"


# ----------------------------------------------------------------------
# Kanonische Auswertung eines Scan-Jobs
# ----------------------------------------------------------------------

def evaluate_scan(job: Dict[str, Any]) -> ScanMonitorReport:
    """
    Bewertet einen Scan-Job für die generischen Monitoring-Endpoints.

    Fängt Fehler selbst ab und liefert dann einen Bericht mit
    state = "error", damit ein einzelner kaputter Job den Sammel-Endpoint
    nicht komplett ausfallen lässt.
    """
    try:
        return _evaluate_scan(job)
    except Exception:
        # Details nur ins Log - die Antwort erreicht Inhaber eines
        # eingeschränkten Monitoring-Tokens.
        slug = str(job.get("slug", "?")) if isinstance(job, dict) else "?"
        logger.exception(f"Auswertung des Scan-Jobs '{slug}' fehlgeschlagen")
        name = str(job.get("name", slug)) if isinstance(job, dict) else slug
        enabled = bool(job.get("enabled", False)) if isinstance(job, dict) else False
        return ScanMonitorReport(
            generated_at=datetime.now(timezone.utc),
            severity=MonitorSeverity.CRITICAL,
            severity_text=severity_text(MonitorSeverity.CRITICAL),
            state=MonitorState.ERROR,
            reasons=[MonitorState.ERROR],
            message=(
                "Zustand konnte nicht ermittelt werden - Details siehe Server-Log"
            ),
            scan=ScanRef(slug=slug, name=name, enabled=enabled),
            run=RunInfo(active=False),
            last_run=LastRunInfo(),
            last_success=LastSuccessInfo(),
            schedule=ScheduleInfo(scheduled=False),
        )


def _evaluate_scan(job: Dict[str, Any]) -> ScanMonitorReport:
    from app.services.scanner import scanner_service
    from app.services.scheduler import scheduler_service
    from app.services.storage import storage

    slug = job["slug"]
    enabled = bool(job["enabled"])

    latest = storage.get_latest_result(slug)
    latest_completed = storage.get_latest_completed_result(slug)
    run_active = scanner_service.is_scan_running(slug)
    job_info = scheduler_service.get_job_info(slug)

    # Alters-Schwellwerte nur für aktivierte Jobs - ein bewusst deaktivierter
    # Job wäre sonst zwangsläufig überfällig. Dieselben Faktoren wie der
    # PRTG-Kanal "Alter letzter Lauf", damit "zu spät" dasselbe bedeutet.
    interval_seconds = (
        scheduler_service.get_expected_interval_seconds(slug) if enabled else None
    )
    limits = age_limits(interval_seconds, 2, 3)
    stale_after = limits["warn_max"]
    overdue_after = limits["err_max"]

    # Einmal ermitteln - der Aufruf baut die Job-Konfiguration nach und ist
    # nicht kostenlos. Wird für die Ordnerbilanz UND die Hängen-Schwelle gebraucht.
    expected_paths = expected_path_count(job)

    # --- Der laufende Scan ---
    started_at = scanner_service.get_scan_started_at(slug)
    active_seconds = age_seconds(started_at) if started_at is not None else None
    stuck_after = stuck_after_seconds(expected_paths)
    stuck = bool(
        run_active and active_seconds is not None and active_seconds > stuck_after
    )
    progress = scanner_service.get_scan_progress(slug) if run_active else None
    run = RunInfo(
        active=run_active,
        started_at=started_at,
        active_seconds=active_seconds,
        progress_percent=(
            compute_progress_percent(progress, latest_completed)
            if progress is not None
            else None
        ),
        current_path=progress.get("current_path") if progress else None,
        stuck_after_seconds=stuck_after,
        stuck=stuck,
        cancel_requested=scanner_service.is_cancel_requested(slug),
    )

    # --- Ordnerzahlen: beziehen sich auf den letzten Lauf ---
    if latest is not None:
        run_ok_items = [item for item in latest.results if item.success]
        run_failed_items = [item for item in latest.results if not item.success]
        folders_ok = len(run_ok_items)
        # Gleiche Formel wie PRTG: nur erfolgreiche Ordner werden persistiert,
        # nach einem Neustart wäre "fehlgeschlagen" sonst fälschlich 0.
        folders_failed = max(expected_paths - folders_ok, len(run_failed_items), 0)
        folders_failed_names = [item.folder_name for item in run_failed_items]
    else:
        folders_ok = 0
        folders_failed = expected_paths
        folders_failed_names = []

    last_run_age = age_seconds(latest.timestamp) if latest is not None else None

    last_run = LastRunInfo(
        at=as_utc(latest.timestamp) if latest is not None else None,
        age_seconds=last_run_age,
        status=latest.status if latest is not None else None,
        error=latest.error if latest is not None else None,
        duration_seconds=(
            sum(item.elapsed_time_ms or 0 for item in latest.results if item.success)
            / 1000.0
            if latest is not None and latest.results
            else None
        ),
        folders_total=folders_ok + folders_failed,
        folders_ok=folders_ok,
        folders_failed=folders_failed,
        folders_failed_names=folders_failed_names,
    )

    # --- Messwerte: aus dem letzten ERFOLGREICHEN Lauf ---
    if latest_completed is not None:
        successful = [item for item in latest_completed.results if item.success]
        last_success = LastSuccessInfo(
            at=as_utc(latest_completed.timestamp),
            age_seconds=age_seconds(latest_completed.timestamp),
            folders_ok=len(successful),
            total_bytes=sum(
                item.total_size.bytes for item in successful if item.total_size
            ),
            total_directories=sum(item.num_dir or 0 for item in successful),
            total_files=sum(item.num_file or 0 for item in successful),
        )
    else:
        last_success = LastSuccessInfo()

    # --- Überfälligkeit ---
    # Ein laufender Scan setzt die Überfälligkeit aus: der Job tut ja gerade,
    # was von ihm erwartet wird.
    overdue = False
    stale = False
    if not run_active and last_run_age is not None:
        if overdue_after is not None and last_run_age > overdue_after:
            overdue = True
        if stale_after is not None and last_run_age > stale_after:
            stale = True
    overdue_by = (
        max(0.0, last_run_age - overdue_after)
        if overdue and last_run_age is not None and overdue_after is not None
        else 0.0
    )

    next_run = job_info.get("next_run") if job_info else None
    schedule = ScheduleInfo(
        scheduled=job_info is not None,
        interval=job.get("interval"),
        expected_interval_seconds=interval_seconds,
        next_run_at=as_utc(next_run) if next_run is not None else None,
        next_run_in_seconds=(
            (as_utc(next_run) - datetime.now(timezone.utc)).total_seconds()
            if next_run is not None
            else None
        ),
        overdue=overdue,
        overdue_by_seconds=overdue_by,
        stale_after_seconds=stale_after,
        overdue_after_seconds=overdue_after,
    )

    # --- Gründe sammeln, Präzedenz entscheidet ---
    reasons: List[MonitorState] = []
    if not enabled:
        reasons.append(MonitorState.DISABLED)
    if stuck:
        reasons.append(MonitorState.STUCK)
    if latest is None:
        reasons.append(MonitorState.NEVER_RUN)
    else:
        if latest.status == "failed":
            reasons.append(MonitorState.FAILED)
        if latest.status == "cancelled":
            reasons.append(MonitorState.CANCELLED)
        if folders_failed > 0:
            reasons.append(MonitorState.PARTIAL)
        if overdue:
            reasons.append(MonitorState.OVERDUE)
        if stale:
            reasons.append(MonitorState.STALE)
    if enabled and job_info is None:
        reasons.append(MonitorState.UNSCHEDULED)

    reasons.sort(key=state_precedence)
    state = reasons[0] if reasons else MonitorState.OK
    # Severity kommt ALLEIN vom state, nicht als Maximum über alle reasons -
    # sonst würde ein deaktivierter Job mit Fehllauf doch alarmieren.
    severity = SEVERITY_BY_STATE[state]

    return ScanMonitorReport(
        generated_at=datetime.now(timezone.utc),
        severity=severity,
        severity_text=severity_text(severity),
        state=state,
        reasons=reasons,
        message=_build_scan_message(
            state=state,
            job_name=job["name"],
            run_active=run_active,
            run=run,
            last_run=last_run,
            last_success=last_success,
            schedule=schedule,
        ),
        scan=ScanRef(slug=slug, name=job["name"], enabled=enabled),
        run=run,
        last_run=last_run,
        last_success=last_success,
        schedule=schedule,
    )


def _build_scan_message(
    *,
    state: MonitorState,
    job_name: str,
    run_active: bool,
    run: RunInfo,
    last_run: LastRunInfo,
    last_success: LastSuccessInfo,
    schedule: ScheduleInfo,
) -> str:
    """Baut den Text, den ein Monitoring-System als Alarmmeldung anzeigt"""
    age = format_age(last_run.age_seconds)

    if state == MonitorState.DISABLED:
        return "Job ist deaktiviert"
    if state == MonitorState.STUCK:
        detail = ""
        if run.progress_percent is not None:
            detail = f" bei {run.progress_percent:.0f} %"
        if run.current_path:
            detail += f", zuletzt '{run.current_path}'"
        hint = (
            " - Abbruch bereits angefordert"
            if run.cancel_requested
            else " - Abbruch über POST /api/scans/<slug>/cancel möglich"
        )
        return (
            f"Scan läuft seit {format_duration(run.active_seconds)} und hängt "
            f"vermutlich{detail}{hint}"
        )
    if state == MonitorState.CANCELLED:
        return f"Letzter Lauf {age} abgebrochen: {last_run.error or 'ohne Angabe'}"
    if state == MonitorState.NEVER_RUN:
        return "Job hat noch keine Ergebnisse geliefert"
    if state == MonitorState.FAILED:
        detail = last_run.error or "unbekannter Fehler"
        return f"Letzter Lauf {age} fehlgeschlagen: {detail}"
    if state == MonitorState.OVERDUE:
        return (
            f"Scan ist überfällig: letzter Lauf {age}, erwartet "
            f"{format_interval(schedule.expected_interval_seconds)}"
        )
    if state == MonitorState.UNSCHEDULED:
        return "Job ist aktiviert, aber nicht im Scheduler eingeplant"
    if state == MonitorState.STALE:
        return (
            f"Letzter Lauf liegt länger zurück als erwartet: {age}, erwartet "
            f"{format_interval(schedule.expected_interval_seconds)}"
        )
    if state == MonitorState.PARTIAL:
        names = ", ".join(last_run.folders_failed_names)
        detail = f": {names}" if names else ""
        return (
            f"Letzter Lauf abgeschlossen, aber {last_run.folders_failed} von "
            f"{last_run.folders_total} Ordnern fehlgeschlagen{detail}"
        )
    if state == MonitorState.ERROR:
        return "Zustand konnte nicht ermittelt werden - Details siehe Server-Log"

    # OK - ein laufender Scan wird zusätzlich erwähnt, ändert aber nichts
    base = (
        f"Letzter Lauf erfolgreich {age}, {last_run.folders_ok} von "
        f"{last_run.folders_total} Ordnern OK"
    )
    if run_active:
        return f"Scan läuft - {base}"
    return base


# ----------------------------------------------------------------------
# Roll-up über alle Scan-Jobs
# ----------------------------------------------------------------------

def evaluate_scans(include_scans: bool = True) -> ScansMonitorReport:
    """
    Bewertet alle Scan-Jobs und rollt sie zu einem Zustand zusammen.

    `severity` ist das Maximum über alle Jobs - damit genügt ein einzelner
    Check für die gesamte Job-Landschaft. `problems` enthält nur die
    auffälligen Jobs, sodass ein Alarmtext ohne Iteration entsteht.
    """
    from app.services.jobs_store import jobs_store

    generated_at = datetime.now(timezone.utc)
    try:
        jobs = jobs_store.list_jobs()
    except Exception:
        logger.exception("Job-Liste für den Monitoring-Bericht nicht lesbar")
        return ScansMonitorReport(
            generated_at=generated_at,
            severity=MonitorSeverity.CRITICAL,
            severity_text=severity_text(MonitorSeverity.CRITICAL),
            state=MonitorState.ERROR,
            message="Job-Liste konnte nicht gelesen werden - Details siehe Server-Log",
            summary=ScansSummary(),
            problems=[],
            scans=[] if include_scans else None,
        )

    reports = [evaluate_scan(job) for job in jobs]

    summary = ScansSummary(total=len(reports))
    for report in reports:
        if report.scan.enabled:
            summary.enabled += 1
        else:
            summary.disabled += 1
        if report.run.active:
            summary.running += 1

        if report.severity == MonitorSeverity.OK:
            summary.ok += 1
        elif report.severity == MonitorSeverity.WARNING:
            summary.warning += 1
        else:
            summary.critical += 1

        # Nach `state` gezählt, nicht nach `reasons` - ein Job zählt genau
        # einmal, und zwar für seinen ausschlaggebenden Grund.
        if report.state == MonitorState.NEVER_RUN:
            summary.never_run += 1
        elif report.state == MonitorState.OVERDUE:
            summary.overdue += 1
        elif report.state == MonitorState.FAILED:
            summary.failed += 1
        elif report.state == MonitorState.PARTIAL:
            summary.partial += 1
        elif report.state == MonitorState.UNSCHEDULED:
            summary.unscheduled += 1
        elif report.state == MonitorState.STUCK:
            summary.stuck += 1
        elif report.state == MonitorState.CANCELLED:
            summary.cancelled += 1

        # Ältester letzter Lauf, nur aktivierte Jobs - deaktivierte laufen
        # bewusst nicht und würden den Wert sonst dauerhaft verzerren.
        if report.scan.enabled and report.last_run.age_seconds is not None:
            if (
                summary.stalest_age_seconds is None
                or report.last_run.age_seconds > summary.stalest_age_seconds
            ):
                summary.stalest_age_seconds = report.last_run.age_seconds
                summary.stalest_slug = report.scan.slug

    problems = [
        ProblemRef(
            slug=report.scan.slug,
            name=report.scan.name,
            severity=report.severity,
            state=report.state,
            message=report.message,
        )
        for report in reports
        if report.severity >= MonitorSeverity.WARNING
    ]
    # Schlimmste zuerst, damit problems[0] den Alarm bestimmt. `min` über die
    # Präzedenz hält die Reihenfolge bei gleicher Severity stabil.
    problems.sort(key=lambda p: (-int(p.severity), state_precedence(p.state)))

    worst = _worst_report(reports)
    if worst is None:
        severity = MonitorSeverity.OK
        state = MonitorState.OK
        message = "Keine Scan-Jobs konfiguriert"
    else:
        severity = worst.severity
        state = worst.state
        summary.worst_slug = worst.scan.slug
        if severity == MonitorSeverity.OK:
            message = (
                "1 Job in Ordnung"
                if summary.total == 1
                else f"Alle {summary.total} Jobs in Ordnung"
            )
        else:
            label = "kritisch" if severity == MonitorSeverity.CRITICAL else "auffällig"
            count = summary.critical if severity == MonitorSeverity.CRITICAL else summary.warning
            message = (
                f"{count} von {summary.total} Jobs {label}: "
                f"{worst.scan.slug} ({worst.message})"
            )

    return ScansMonitorReport(
        generated_at=generated_at,
        severity=severity,
        severity_text=severity_text(severity),
        state=state,
        message=message,
        summary=summary,
        problems=problems,
        scans=reports if include_scans else None,
    )


def _worst_report(reports: List[ScanMonitorReport]) -> Optional[ScanMonitorReport]:
    """Der ausschlaggebende Job: höchste Severity, bei Gleichstand nach Präzedenz"""
    if not reports:
        return None
    return max(
        reports,
        key=lambda r: (int(r.severity), -state_precedence(r.state)),
    )


# ----------------------------------------------------------------------
# Infrastruktur-Bericht
# ----------------------------------------------------------------------

async def evaluate_server() -> ServerMonitorReport:
    """
    Bewertet die Infrastruktur: Scheduler, Systemressourcen, Konfiguration.

    Job-Ergebnisse gehen bewusst NICHT in die Severity ein - sonst alarmieren
    dieser Bericht und /api/monitor/scans für dieselbe Ursache. Die Job-Zähler
    sind rein informativ.
    """
    from app.services.health import (
        SERVER_VERSION,
        collect_config_warnings,
        collect_job_health,
        collect_scheduler_metrics,
        collect_system_raw,
        get_server_start_time,
        get_uptime_seconds,
    )
    from app.services.storage import storage

    generated_at = datetime.now(timezone.utc)
    try:
        # In einem Thread, weil psutil.cpu_percent bewusst 100 ms blockiert.
        raw_system = await asyncio.to_thread(collect_system_raw)
        scheduler_metrics = collect_scheduler_metrics()
        jobs_health = collect_job_health()
        warnings = collect_config_warnings()
        storage_stats = storage.get_storage_stats()
    except Exception:
        logger.exception("Serverzustand konnte nicht ermittelt werden")
        return ServerMonitorReport(
            generated_at=generated_at,
            severity=MonitorSeverity.CRITICAL,
            severity_text=severity_text(MonitorSeverity.CRITICAL),
            state=ServerState.ERROR,
            message="Serverzustand nicht ermittelbar - Details siehe Server-Log",
            server=ServerInfo(version=SERVER_VERSION),
            scheduler=SchedulerInfo(),
            system=SystemInfo(),
            storage=StorageInfo(),
            jobs=JobsInfo(),
            warnings=[],
        )

    # Ohne psutil bleiben alle Werte null statt 0 - "0 % Disk belegt" wäre
    # eine gefährliche Fehldeutung.
    if raw_system is not None:
        system = SystemInfo(
            available=True,
            cpu_percent=raw_system["cpu_percent"],
            memory_percent=raw_system["mem_percent"],
            memory_available_bytes=raw_system["mem_available"],
            disk_percent=raw_system["disk_percent"],
            disk_free_bytes=raw_system["disk_free"],
        )
    else:
        system = SystemInfo(available=False)

    scheduler_running = bool(scheduler_metrics.get("running"))
    resource_values = [
        value
        for value in (system.memory_percent, system.disk_percent)
        if value is not None
    ]
    worst_resource = max(resource_values) if resource_values else None

    if not scheduler_running:
        state = ServerState.SCHEDULER_DOWN
        message = "Scheduler läuft nicht - es werden keine Scans ausgeführt"
    elif worst_resource is not None and worst_resource >= 95:
        state = ServerState.RESOURCES_CRITICAL
        message = f"Systemressourcen kritisch: {worst_resource:.0f} % belegt"
    elif worst_resource is not None and worst_resource >= 85:
        state = ServerState.RESOURCES_WARNING
        message = f"Systemressourcen knapp: {worst_resource:.0f} % belegt"
    elif warnings:
        state = ServerState.CONFIG_WARNINGS
        count = len(warnings)
        message = f"Die Konfiguration enthält {count} Warnung{'en' if count != 1 else ''}"
    else:
        state = ServerState.OK
        message = "Server in Ordnung"

    severity = SEVERITY_BY_SERVER_STATE[state]
    start_time = get_server_start_time()

    return ServerMonitorReport(
        generated_at=generated_at,
        severity=severity,
        severity_text=severity_text(severity),
        state=state,
        message=message,
        server=ServerInfo(
            version=SERVER_VERSION,
            uptime_seconds=get_uptime_seconds(),
            start_time=start_time,
        ),
        scheduler=SchedulerInfo(
            running=scheduler_running,
            total_jobs=scheduler_metrics.get("total_jobs", 0),
            enabled_jobs=scheduler_metrics.get("enabled_jobs", 0),
        ),
        system=system,
        storage=StorageInfo(
            db_size_bytes=storage_stats.get("db_size_bytes"),
            results_total=storage_stats.get("total_results_db"),
            oldest_entry=storage_stats.get("oldest_entry"),
            newest_entry=storage_stats.get("newest_entry"),
        ),
        jobs=JobsInfo(
            total=jobs_health.get("total", 0),
            enabled=jobs_health.get("enabled", 0),
            running=jobs_health.get("running", 0),
            failed=jobs_health.get("failed", 0),
            without_results=jobs_health.get("without_results", 0),
        ),
        warnings=warnings,
    )


# ----------------------------------------------------------------------
# Instanz-Bericht
# ----------------------------------------------------------------------

async def evaluate_instance() -> InstanceMonitorReport:
    """
    Gesamtzustand: Maximum aus Infrastruktur und Job-Landschaft.

    Der Endpoint für "ein Werkzeug, ein Check". Die Einzelberichte der Jobs
    bleiben weg - wer sie braucht, fragt /api/monitor/scans.
    """
    generated_at = datetime.now(timezone.utc)
    server = await evaluate_server()
    scans = evaluate_scans(include_scans=False)

    components = {
        "server": ComponentRef(
            severity=server.severity,
            severity_text=server.severity_text,
            state=server.state.value,
            message=server.message,
        ),
        "scans": ComponentRef(
            severity=scans.severity,
            severity_text=scans.severity_text,
            state=scans.state.value,
            message=scans.message,
        ),
    }

    # Bei Gleichstand gewinnt die Infrastruktur: ein stehender Scheduler ist
    # die Ursache, auffällige Jobs sind dann nur die Folge.
    leading = server if server.severity >= scans.severity else scans
    severity = leading.severity

    if severity == MonitorSeverity.OK:
        message = "Alles in Ordnung"
    else:
        message = leading.message

    return InstanceMonitorReport(
        generated_at=generated_at,
        severity=severity,
        severity_text=severity_text(severity),
        state=leading.state.value,
        message=message,
        components=components,
        problems=scans.problems,
    )
