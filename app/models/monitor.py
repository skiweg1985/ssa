"""Modelle der generischen Monitoring-Endpoints.

Schema-Grundsätze (bewusst anders als bei den PRTG-Modellen):

1. `severity` ist die einzige Achse, die ein Monitoring-System auswerten muss:
   0 = OK, 1 = WARNING, 2 = CRITICAL. Streng monoton, damit ">= 1" bzw. ">= 2"
   immer als Schwellwert funktioniert. Ein UNKNOWN(3) wie bei Nagios wird
   absichtlich NIE geliefert - es wäre nicht monoton.
2. `state` nennt den Grund, `reasons` alle zutreffenden Gründe.
3. Alle Felder sind IMMER vorhanden; Unbekanntes ist `null`. Deshalb darf an
   den Routen kein `response_model_exclude_none` gesetzt werden - sonst bricht
   JSONPath in Zabbix/Grafana je nach Zustand weg.
"""
from datetime import datetime
from enum import Enum, IntEnum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MonitorSeverity(IntEnum):
    """Alarmachse - deckungsgleich mit Nagios OK/WARNING/CRITICAL"""
    OK = 0
    WARNING = 1
    CRITICAL = 2


class MonitorState(str, Enum):
    """Grund für die Severity. Reihenfolge hier = Reihenfolge der Auswertung."""
    ERROR = "error"                # Auswertung selbst fehlgeschlagen
    DISABLED = "disabled"          # Job bewusst deaktiviert -> kein Alarm
    STUCK = "stuck"                # läuft ungewöhnlich lange -> hängt vermutlich
    FAILED = "failed"              # letzter beendeter Lauf fehlgeschlagen
    OVERDUE = "overdue"            # deutlich überfällig
    NEVER_RUN = "never_run"        # noch keine Ergebnisse
    UNSCHEDULED = "unscheduled"    # aktiv, aber nicht eingeplant
    CANCELLED = "cancelled"        # letzter Lauf wurde abgebrochen
    STALE = "stale"                # länger nicht gelaufen als erwartet
    PARTIAL = "partial"            # Lauf ok, aber Ordner fehlgeschlagen
    OK = "ok"


class ServerState(str, Enum):
    """Grund für die Severity des Server-Berichts (nur Infrastruktur)"""
    ERROR = "error"
    SCHEDULER_DOWN = "scheduler_down"
    RESOURCES_CRITICAL = "resources_critical"
    RESOURCES_WARNING = "resources_warning"
    CONFIG_WARNINGS = "config_warnings"
    OK = "ok"


SEVERITY_BY_STATE: Dict[MonitorState, MonitorSeverity] = {
    MonitorState.ERROR: MonitorSeverity.CRITICAL,
    # Ein absichtlich deaktivierter Job darf nie alarmieren - deshalb OK,
    # obwohl "disabled" in der Kaskade Vorrang vor Fehlergründen hat.
    MonitorState.DISABLED: MonitorSeverity.OK,
    # Ein hängender Lauf ist kritisch: solange er als laufend gilt, setzt er
    # die Überfälligkeit aus - das Monitoring wäre sonst dauerhaft blind.
    MonitorState.STUCK: MonitorSeverity.CRITICAL,
    MonitorState.FAILED: MonitorSeverity.CRITICAL,
    MonitorState.OVERDUE: MonitorSeverity.CRITICAL,
    MonitorState.NEVER_RUN: MonitorSeverity.WARNING,
    MonitorState.UNSCHEDULED: MonitorSeverity.WARNING,
    # Abbruch war eine bewusste Handlung - keine frischen Daten, aber kein
    # Fehler, der jemanden aus dem Bett holen müsste.
    MonitorState.CANCELLED: MonitorSeverity.WARNING,
    MonitorState.STALE: MonitorSeverity.WARNING,
    MonitorState.PARTIAL: MonitorSeverity.WARNING,
    MonitorState.OK: MonitorSeverity.OK,
}

SEVERITY_BY_SERVER_STATE: Dict[ServerState, MonitorSeverity] = {
    ServerState.ERROR: MonitorSeverity.CRITICAL,
    ServerState.SCHEDULER_DOWN: MonitorSeverity.CRITICAL,
    ServerState.RESOURCES_CRITICAL: MonitorSeverity.CRITICAL,
    ServerState.RESOURCES_WARNING: MonitorSeverity.WARNING,
    ServerState.CONFIG_WARNINGS: MonitorSeverity.WARNING,
    ServerState.OK: MonitorSeverity.OK,
}

_SEVERITY_TEXT = {
    MonitorSeverity.OK: "ok",
    MonitorSeverity.WARNING: "warning",
    MonitorSeverity.CRITICAL: "critical",
}


def severity_text(severity: MonitorSeverity) -> str:
    """Menschenlesbare Form der Severity ("ok" | "warning" | "critical")"""
    return _SEVERITY_TEXT[MonitorSeverity(severity)]


# ----------------------------------------------------------------------
# Bausteine des Job-Berichts
# ----------------------------------------------------------------------

class ScanRef(BaseModel):
    """Identität des Jobs - ohne Verwaltungsdaten (NAS, Shares, Pfade)"""
    slug: str = Field(..., description="Slug des Scan-Jobs")
    name: str = Field(..., description="Anzeigename des Scan-Jobs")
    enabled: bool = Field(..., description="Ob der Job aktiviert ist")


class RunInfo(BaseModel):
    """
    Der laufende Scan - eine EIGENE Achse.

    "Läuft gerade" ist absichtlich kein `state`: sonst verdeckt es das Ergebnis
    des vorherigen Laufs und das Monitoring wäre während jedes Laufs blind.
    Ein laufender Scan kann die Severity nie verschlechtern.
    """
    active: bool = Field(..., description="Ob gerade ein Scan dieses Jobs läuft")
    started_at: Optional[datetime] = Field(
        None, description="Startzeitpunkt des laufenden Scans"
    )
    active_seconds: Optional[float] = Field(
        None, description="Bisherige Laufzeit des laufenden Scans in Sekunden"
    )
    progress_percent: Optional[float] = Field(
        None, description="Fortschritt in Prozent, sofern ermittelbar"
    )
    current_path: Optional[str] = Field(
        None, description="Gerade gescannter Pfad"
    )
    stuck_after_seconds: Optional[float] = Field(
        None,
        description=(
            "Ab dieser Laufzeit gilt der Lauf als hängend. Abgeleitet aus der "
            "Pfadanzahl (je Pfad gilt ein Timeout von 300 s), verdoppelt als "
            "Puffer, mindestens 30 Minuten"
        ),
    )
    stuck: bool = Field(
        False, description="Ob der laufende Scan die Hängen-Schwelle überschritten hat"
    )
    cancel_requested: bool = Field(
        False, description="Ob für diesen Lauf ein Abbruch angefordert wurde"
    )


class LastRunInfo(BaseModel):
    """
    Der letzte BEENDETE Lauf - egal ob erfolgreich.

    Die Ordnerzahlen stehen hier (nicht in `last_success`), damit eindeutig ist,
    auf welchen Lauf sie sich beziehen.
    """
    at: Optional[datetime] = Field(None, description="Zeitpunkt des letzten Laufs")
    age_seconds: Optional[float] = Field(None, description="Alter des letzten Laufs")
    status: Optional[str] = Field(
        None, description="Roher Lauf-Status: 'completed' | 'failed' | 'running'"
    )
    error: Optional[str] = Field(None, description="Fehlermeldung des letzten Laufs")
    duration_seconds: Optional[float] = Field(
        None, description="Summierte Scan-Dauer des letzten erfolgreichen Laufs"
    )
    folders_total: int = Field(0, description="Erwartete Anzahl Ordner")
    folders_ok: int = Field(0, description="Erfolgreich gescannte Ordner")
    folders_failed: int = Field(0, description="Fehlgeschlagene Ordner")
    folders_failed_names: List[str] = Field(
        default_factory=list, description="Namen der fehlgeschlagenen Ordner"
    )


class LastSuccessInfo(BaseModel):
    """
    Messwerte aus dem letzten ERFOLGREICHEN Lauf.

    Ein Fehllauf setzt `severity` auf 2, lässt diese Werte aber stehen - so
    reißen die Charts eines Monitoring-Systems nicht auf 0.
    """
    at: Optional[datetime] = Field(None, description="Zeitpunkt des letzten Erfolgs")
    age_seconds: Optional[float] = Field(None, description="Alter der letzten Daten")
    folders_ok: int = Field(0, description="Ordner mit Messwerten")
    total_bytes: Optional[int] = Field(None, description="Gesamtgröße in Bytes")
    total_directories: Optional[int] = Field(None, description="Anzahl Verzeichnisse")
    total_files: Optional[int] = Field(None, description="Anzahl Dateien")


class ScheduleInfo(BaseModel):
    """
    Zeitplan und Überfälligkeit - serverseitig ausgerechnet.

    Der Client muss weder `interval` parsen (Cron ODER Kurzform wie "10m") noch
    Schwellwerte selbst bilden. `scheduled` trennt die Bedeutungen, die im alten
    Endpoint alle als `next_run: null` erschienen.
    """
    scheduled: bool = Field(..., description="Ob der Job im Scheduler eingeplant ist")
    interval: Optional[str] = Field(None, description="Konfiguriertes Intervall (roh)")
    expected_interval_seconds: Optional[float] = Field(
        None, description="Erwarteter Abstand zweier Läufe in Sekunden"
    )
    next_run_at: Optional[datetime] = Field(None, description="Nächster geplanter Lauf")
    next_run_in_seconds: Optional[float] = Field(
        None, description="Sekunden bis zum nächsten Lauf"
    )
    overdue: bool = Field(False, description="Ob der Job deutlich überfällig ist")
    overdue_by_seconds: float = Field(
        0, description="Überschreitung der Überfälligkeitsschwelle in Sekunden"
    )
    stale_after_seconds: Optional[float] = Field(
        None, description="Ab diesem Alter gilt der Lauf als veraltet (Warnung)"
    )
    overdue_after_seconds: Optional[float] = Field(
        None, description="Ab diesem Alter gilt der Job als überfällig (kritisch)"
    )


class ScanMonitorReport(BaseModel):
    """Monitoring-Bericht eines einzelnen Scan-Jobs"""
    schema_version: str = Field(
        "ssa.monitor.scan/1", description="Version dieses Antwortschemas"
    )
    generated_at: datetime = Field(..., description="Zeitpunkt der Auswertung")
    severity: MonitorSeverity = Field(..., description="0 = OK, 1 = Warnung, 2 = kritisch")
    severity_text: str = Field(..., description="'ok' | 'warning' | 'critical'")
    state: MonitorState = Field(..., description="Schwerwiegendster zutreffender Grund")
    reasons: List[MonitorState] = Field(
        default_factory=list,
        description="Alle zutreffenden Gründe in Auswertungsreihenfolge (reasons[0] == state)",
    )
    message: str = Field(..., description="Menschenlesbare Zusammenfassung")
    scan: ScanRef
    run: RunInfo
    last_run: LastRunInfo
    last_success: LastSuccessInfo
    schedule: ScheduleInfo


# ----------------------------------------------------------------------
# Sammel-Bericht über alle Jobs
# ----------------------------------------------------------------------

class ProblemRef(BaseModel):
    """Kurzform eines auffälligen Jobs - für Alarmtexte ohne Iteration"""
    slug: str
    name: str
    severity: MonitorSeverity
    state: MonitorState
    message: str


class ScansSummary(BaseModel):
    """Zähler über alle Jobs"""
    total: int = 0
    enabled: int = 0
    disabled: int = 0
    running: int = 0
    ok: int = 0
    warning: int = 0
    critical: int = 0
    never_run: int = 0
    overdue: int = 0
    failed: int = 0
    partial: int = 0
    unscheduled: int = 0
    stuck: int = 0
    cancelled: int = 0
    worst_slug: Optional[str] = Field(None, description="Slug des schlimmsten Jobs")
    stalest_slug: Optional[str] = Field(None, description="Job mit dem ältesten Lauf")
    stalest_age_seconds: Optional[float] = Field(None, description="Alter dieses Laufs")


class ScansMonitorReport(BaseModel):
    """Bericht über alle Scan-Jobs - `severity` ist das Maximum über alle Jobs"""
    schema_version: str = Field("ssa.monitor.scans/1")
    generated_at: datetime
    severity: MonitorSeverity
    severity_text: str
    state: MonitorState
    message: str
    summary: ScansSummary
    problems: List[ProblemRef] = Field(default_factory=list)
    scans: Optional[List[ScanMonitorReport]] = Field(
        None, description="Vollständige Job-Berichte; null bei include_scans=0"
    )


# ----------------------------------------------------------------------
# Server-Bericht (nur Infrastruktur)
# ----------------------------------------------------------------------

class ServerInfo(BaseModel):
    version: str
    uptime_seconds: Optional[float] = None
    start_time: Optional[datetime] = None


class SchedulerInfo(BaseModel):
    running: bool = False
    total_jobs: int = 0
    enabled_jobs: int = 0


class SystemInfo(BaseModel):
    """
    Systemressourcen. Ohne psutil ist `available` false und ALLE Werte sind
    null - nicht 0, das würde als "0 % Disk belegt" fehlgedeutet.
    """
    available: bool = False
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    memory_available_bytes: Optional[int] = None
    disk_percent: Optional[float] = None
    disk_free_bytes: Optional[int] = None


class StorageInfo(BaseModel):
    db_size_bytes: Optional[int] = None
    results_total: Optional[int] = None
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None


class JobsInfo(BaseModel):
    """Job-Zähler - hier rein informativ, geht NICHT in die Server-Severity ein"""
    total: int = 0
    enabled: int = 0
    running: int = 0
    failed: int = 0
    without_results: int = 0


class ServerMonitorReport(BaseModel):
    """
    Infrastruktur-Bericht: Scheduler, Systemressourcen, Storage, Konfiguration.

    Job-Ergebnisse gehen bewusst NICHT in die Severity ein - sonst alarmieren
    dieser Bericht und /api/monitor/scans für dieselbe Ursache.
    """
    schema_version: str = Field("ssa.monitor.server/1")
    generated_at: datetime
    severity: MonitorSeverity
    severity_text: str
    state: ServerState
    message: str
    server: ServerInfo
    scheduler: SchedulerInfo
    system: SystemInfo
    storage: StorageInfo
    jobs: JobsInfo
    warnings: List[Dict[str, str]] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Instanz-Bericht (ein Check für alles)
# ----------------------------------------------------------------------

class ComponentRef(BaseModel):
    severity: MonitorSeverity
    severity_text: str
    state: str
    message: str


class InstanceMonitorReport(BaseModel):
    """Gesamtzustand: `severity` = Maximum aus Server- und Scans-Bericht"""
    schema_version: str = Field("ssa.monitor.instance/1")
    generated_at: datetime
    severity: MonitorSeverity
    severity_text: str
    state: str = Field(..., description="State der ausschlaggebenden Komponente")
    message: str
    components: Dict[str, ComponentRef]
    problems: List[ProblemRef] = Field(default_factory=list)
