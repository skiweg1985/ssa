"""Scheduler Service - APScheduler Integration"""
import asyncio
import logging
import os
import random
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Union
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.services.scanner import scanner_service
from app.models.config import ScanTaskConfigYAML
from app.models.scan import RetryInfo, ScanResult

logger = logging.getLogger(__name__)

DEFAULT_SCAN_RETRY_COUNT = 2
DEFAULT_SCAN_RETRY_DELAY_SECONDS = 300
SCAN_RETRY_JITTER_SECONDS = 30
MAX_SCAN_RETRY_COUNT = 10
MIN_SCAN_RETRY_DELAY_SECONDS = 10
MAX_SCAN_RETRY_DELAY_SECONDS = 86400


@dataclass(frozen=True)
class ScanRetryPolicy:
    """Globale Retry-Policy für geplante Scan-Jobs."""

    count: int
    delay_seconds: int


@dataclass
class _RetrySequence:
    """Interner, abbrechbarer Kontext einer geplanten Ausführung."""

    cancel_event: asyncio.Event
    loop: asyncio.AbstractEventLoop


def _bounded_env_int(
    name: str, default: int, minimum: int, maximum: int
) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"Ungültiger Wert für {name}={raw!r}; verwende Default {default}"
        )
        return default
    if value < minimum or value > maximum:
        logger.warning(
            f"{name}={value} außerhalb {minimum}..{maximum}; "
            f"verwende Default {default}"
        )
        return default
    return value


def get_scan_retry_policy() -> ScanRetryPolicy:
    """Liest und validiert die globale Retry-Policy aus der Umgebung."""

    return ScanRetryPolicy(
        count=_bounded_env_int(
            "SSA_SCAN_RETRY_COUNT",
            DEFAULT_SCAN_RETRY_COUNT,
            0,
            MAX_SCAN_RETRY_COUNT,
        ),
        delay_seconds=_bounded_env_int(
            "SSA_SCAN_RETRY_DELAY_SECONDS",
            DEFAULT_SCAN_RETRY_DELAY_SECONDS,
            MIN_SCAN_RETRY_DELAY_SECONDS,
            MAX_SCAN_RETRY_DELAY_SECONDS,
        ),
    )


def _retry_reason(result: ScanResult) -> Optional[str]:
    """Liefert den Retry-Grund oder None für ein endgültiges Ergebnis."""

    if result.status == "failed":
        return "failed"
    if result.status == "completed" and any(not item.success for item in result.results):
        return "partial"
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_interval_string(interval_str: str) -> Optional[timedelta]:
    """
    Parst ein Interval-String im Format "10s", "10m", "10h" etc.
    
    Args:
        interval_str: String im Format "NUMBERs", "NUMBERm", "NUMBERh", "NUMBERd"
                     (s = Sekunden, m = Minuten, h = Stunden, d = Tage)
    
    Returns:
        timedelta Objekt oder None bei ungültigem Format
    """
    # Regex-Pattern für Interval-Format: Zahl gefolgt von Einheit
    pattern = r'^(\d+)([smhd])$'
    match = re.match(pattern, interval_str.lower().strip())
    
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)

    # Ein Intervall von 0 wuerde APScheduler dauerfeuern lassen
    if value == 0:
        return None

    # Konvertiere in timedelta.
    # timedelta wirft OverflowError, sobald der Wert nicht mehr in einen
    # C-int passt ("99999999999999999999d"). Das ist eine ungueltige Eingabe
    # wie jede andere - hier abfangen, damit die Validierung 422 liefert
    # statt den Fehler bis in einen 500er durchzureichen.
    try:
        if unit == 's':
            return timedelta(seconds=value)
        elif unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
    except OverflowError:
        return None

    return None


class SchedulerService:
    """Service für automatisches Scheduling von Scans"""
    
    def __init__(self):
        """Initialisiert den Scheduler Service"""
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': True,  # Wenn ein Job verpasst wurde, führe nur einmal aus
            'max_instances': 1,  # Nur eine Instanz pro Job gleichzeitig
            'misfire_grace_time': 3600  # 1 Stunde Grace Time für verpasste Jobs
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults
        )
        self._job_ids: Dict[str, str] = {}  # Mapping von scan_slug zu job_id
        self._retry_lock = threading.Lock()
        self._retry_states: Dict[str, RetryInfo] = {}
        self._retry_sequences: Dict[str, _RetrySequence] = {}

    def get_retry_info(self, scan_slug: str) -> RetryInfo:
        """Gibt eine threadsichere Momentaufnahme des Retry-Zustands zurück."""

        with self._retry_lock:
            info = self._retry_states.get(scan_slug)
            if info is not None:
                return info.model_copy(deep=True)
        return RetryInfo(max_attempts=get_scan_retry_policy().count)

    def _begin_retry_sequence(self, scan_slug: str) -> _RetrySequence:
        sequence = _RetrySequence(
            cancel_event=asyncio.Event(),
            loop=asyncio.get_running_loop(),
        )
        previous = None
        with self._retry_lock:
            previous = self._retry_sequences.get(scan_slug)
            self._retry_sequences[scan_slug] = sequence
            self._retry_states.pop(scan_slug, None)
        if previous is not None:
            previous.loop.call_soon_threadsafe(previous.cancel_event.set)
        return sequence

    def _sequence_is_current(
        self, scan_slug: str, sequence: _RetrySequence
    ) -> bool:
        with self._retry_lock:
            return self._retry_sequences.get(scan_slug) is sequence

    def _set_retry_info(
        self,
        scan_slug: str,
        sequence: _RetrySequence,
        info: RetryInfo,
    ) -> bool:
        with self._retry_lock:
            if self._retry_sequences.get(scan_slug) is not sequence:
                return False
            self._retry_states[scan_slug] = info
            return True

    def _finish_retry_sequence(
        self, scan_slug: str, sequence: _RetrySequence
    ) -> None:
        with self._retry_lock:
            if self._retry_sequences.get(scan_slug) is sequence:
                self._retry_sequences.pop(scan_slug, None)
                self._retry_states.pop(scan_slug, None)

    def cancel_retry_sequence(self, scan_slug: str, reason: str) -> bool:
        """
        Hebt einen wartenden Scheduler-Retry auf.

        Die laufende Scanner-Instanz wird weiterhin über request_cancel()
        beendet; diese Methode weckt nur eine wartende Retry-Schleife auf und
        verhindert weitere Versuche.
        """

        with self._retry_lock:
            sequence = self._retry_sequences.pop(scan_slug, None)
            retry_was_visible = self._retry_states.pop(scan_slug, None) is not None
        if sequence is None:
            return False
        logger.info(f"Retry-Sequenz für Scan '{scan_slug}' aufgehoben: {reason}")
        sequence.loop.call_soon_threadsafe(sequence.cancel_event.set)
        return retry_was_visible

    def _next_regular_run(self, scan_slug: str) -> Optional[datetime]:
        job_id = self._job_ids.get(scan_slug)
        if job_id is None:
            return None
        job = self.scheduler.get_job(job_id)
        if job is None:
            return None
        return getattr(job, "next_run_time", None)

    @staticmethod
    async def _wait_for_retry(
        sequence: _RetrySequence, delay_seconds: int
    ) -> bool:
        """Wartet abbrechbar; True bedeutet, dass die Sequenz aufgehoben wurde."""

        try:
            await asyncio.wait_for(
                sequence.cancel_event.wait(), timeout=delay_seconds
            )
            return True
        except asyncio.TimeoutError:
            return False

    def load_and_schedule(self) -> None:
        """Lädt alle aktivierten Scan-Jobs aus der Datenbank und plant sie ein."""
        try:
            from app.services.jobs_store import jobs_store

            jobs = jobs_store.list_jobs()
            logger.info(f"Jobs aus Datenbank geladen: {len(jobs)} Scan-Task(s) gefunden")

            for job in jobs:
                if job["enabled"]:
                    try:
                        scan_config = jobs_store.to_scan_config(job)
                        self.add_scan_job(scan_config)
                    except Exception as e:
                        logger.error(
                            f"Job '{job['slug']}' konnte nicht eingeplant werden: {e}"
                        )
                else:
                    logger.info(f"Scan '{job['name']}' ist deaktiviert, überspringe")

        except Exception as e:
            logger.error(f"Fehler beim Laden der Jobs aus der Datenbank: {e}")
            raise
    
    def _create_trigger(self, interval_str: str, scan_name: str) -> Optional[Union[CronTrigger, IntervalTrigger]]:
        """
        Erstellt einen Trigger basierend auf dem Interval-String.
        Unterstützt sowohl Cron-Format als auch einfache Interval-Formate (10s, 10m, 10h, etc.)
        
        Args:
            interval_str: Interval-String (Cron-Format oder Interval-Format)
            scan_name: Name des Scans (für Fehlermeldungen)
        
        Returns:
            Trigger-Objekt oder None bei Fehler
        """
        # Versuche zuerst, ob es ein Interval-Format ist (z.B. "10s", "10m", "10h")
        interval_delta = parse_interval_string(interval_str)
        if interval_delta is not None:
            logger.info(f"Erkenne Interval-Format für Scan '{scan_name}': {interval_str}")
            # Extrahiere Wert und Einheit direkt aus dem String
            pattern = r'^(\d+)([smhd])$'
            match = re.match(pattern, interval_str.lower().strip())
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                
                # Erstelle IntervalTrigger mit der entsprechenden Einheit
                if unit == 's':
                    trigger = IntervalTrigger(seconds=value)
                elif unit == 'm':
                    trigger = IntervalTrigger(minutes=value)
                elif unit == 'h':
                    trigger = IntervalTrigger(hours=value)
                elif unit == 'd':
                    trigger = IntervalTrigger(days=value)
                else:
                    logger.error(f"Unbekannte Einheit '{unit}' für Scan '{scan_name}'")
                    return None
                
                logger.info(f"IntervalTrigger erstellt: {value} {unit} für Scan '{scan_name}'")
                return trigger
        
        # Ansonsten versuche Cron-Format
        cron_parts = interval_str.split()
        if len(cron_parts) == 5:
            logger.info(f"Erkenne Cron-Format für Scan '{scan_name}': {interval_str}")
            try:
                return CronTrigger(
                    minute=cron_parts[0],
                    hour=cron_parts[1],
                    day=cron_parts[2],
                    month=cron_parts[3],
                    day_of_week=cron_parts[4]
                )
            except Exception as e:
                logger.error(f"Ungültiges Cron-Format für Scan '{scan_name}': {e}")
                return None
        
        # Weder Interval noch Cron-Format erkannt
        logger.error(
            f"Ungültiges Interval-Format für Scan '{scan_name}': {interval_str}. "
            f"Erwartet wird entweder Cron-Format (z.B. '0 */6 * * *') oder "
            f"Interval-Format (z.B. '10s', '10m', '10h', '10d')"
        )
        return None
    
    def add_scan_job(self, scan_config: ScanTaskConfigYAML) -> Optional[str]:
        """
        Fügt einen Scan-Job zum Scheduler hinzu
        
        Args:
            scan_config: Scan-Konfiguration
        
        Returns:
            Job-ID oder None bei Fehler
        """
        try:
            # Erstelle Trigger (unterstützt sowohl Cron als auch Interval-Format)
            trigger = self._create_trigger(scan_config.interval, scan_config.name)
            if trigger is None:
                return None
            
            # Erstelle Job
            job_id = f"scan_{scan_config.slug}"
            
            # Entferne existierenden Job falls vorhanden
            if scan_config.slug in self._job_ids:
                self.remove_scan_job(scan_config.slug)
            
            self.scheduler.add_job(
                func=self._run_scan_job,
                trigger=trigger,
                id=job_id,
                name=f"Scan: {scan_config.name}",
                args=[scan_config],
                replace_existing=True
            )
            
            self._job_ids[scan_config.slug] = job_id

            # Berechne nächsten Lauf
            next_run = self.scheduler.get_job(job_id).next_run_time if self.scheduler.running else None
            
            # Erstelle detaillierte Logging-Ausgabe mit allen zu scannenden Pfaden
            paths_info = []
            if scan_config.paths:
                paths_info.extend([f"path:{p}" for p in scan_config.paths])
            if scan_config.shares:
                if scan_config.folders:
                    for share in scan_config.shares:
                        for folder in scan_config.folders:
                            paths_info.append(f"share:{share}/folder:{folder}")
                else:
                    paths_info.extend([f"share:{s}" for s in scan_config.shares])
            
            trigger_type = "IntervalTrigger" if isinstance(trigger, IntervalTrigger) else "CronTrigger"
            logger.info(
                f"Job für Scan '{scan_config.name}' hinzugefügt. "
                f"Intervall: {scan_config.interval} ({trigger_type}), Nächster Lauf: {next_run}, "
                f"Zu scannende Pfade: {', '.join(paths_info) if paths_info else 'Keine'}"
            )
            
            return job_id
        
        except Exception as e:
            logger.error(f"Fehler beim Hinzufügen des Jobs für Scan '{scan_config.name}': {e}")
            return None
    
    def remove_scan_job(self, scan_slug: str) -> bool:
        """
        Entfernt einen Scan-Job vom Scheduler
        
        Args:
            scan_slug: Slug des Scans
        
        Returns:
            True wenn erfolgreich entfernt
        """
        self.cancel_retry_sequence(scan_slug, "Job entfernt oder neu eingeplant")
        job_id = self._job_ids.get(scan_slug)
        if job_id is None:
            return False

        try:
            self.scheduler.remove_job(job_id)
            self._job_ids.pop(scan_slug, None)
            logger.info(f"Job für Scan '{scan_slug}' entfernt")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Entfernen des Jobs für Scan '{scan_slug}': {e}")
            return False
    
    async def _run_scan_job(self, scan_config: ScanTaskConfigYAML) -> None:
        """
        Führt einen Scan-Job aus (wird vom Scheduler aufgerufen)
        
        Args:
            scan_config: Scan-Konfiguration
        """
        from app.services.jobs_store import jobs_store
        from app.services.storage import storage

        scan_slug = scan_config.slug
        policy = get_scan_retry_policy()
        sequence = self._begin_retry_sequence(scan_slug)
        current_config = scan_config
        logger.info(
            f"=== Scheduler: Starte geplanten Scan '{scan_config.name}' === "
            f"(max. {policy.count} Retries)"
        )

        try:
            for attempt_index in range(policy.count + 1):
                if not self._sequence_is_current(scan_slug, sequence):
                    return

                attempt_started = datetime.now(timezone.utc)
                result = None
                reason = None
                failure_timestamp = attempt_started

                try:
                    result = await scanner_service.run_scan(current_config)
                    reason = _retry_reason(result)
                    failure_timestamp = _as_utc(result.timestamp)
                except Exception as exc:
                    reason = "failed"
                    logger.exception(
                        f"Scheduler-Versuch für Scan '{current_config.name}' "
                        f"ist unerwartet abgebrochen: {exc}"
                    )

                duration = (
                    datetime.now(timezone.utc) - attempt_started
                ).total_seconds()
                if result is not None and reason is None:
                    if result.status == "completed":
                        logger.info(
                            f"=== Scheduler: Scan '{current_config.name}' "
                            f"erfolgreich abgeschlossen === Dauer: {duration:.1f}s, "
                            f"Ergebnisse: {len(result.results)} Pfad(e)"
                        )
                    else:
                        logger.warning(
                            f"=== Scheduler: Scan '{current_config.name}' mit "
                            f"Status '{result.status}' beendet === Dauer: {duration:.1f}s"
                        )
                    return

                retry_number = attempt_index + 1
                if retry_number > policy.count:
                    logger.error(
                        f"Scheduler: Scan '{current_config.name}' bleibt nach "
                        f"{policy.count} Retry(s) fehlerhaft "
                        f"(Grund: {reason or 'failed'})"
                    )
                    return

                job = jobs_store.get_job(scan_slug)
                if job is None or not job["enabled"]:
                    logger.info(
                        f"Scheduler: Kein Retry für Scan '{scan_slug}': "
                        "Job wurde gelöscht oder deaktiviert"
                    )
                    return

                latest = storage.get_latest_result(scan_slug)
                if (
                    latest is not None
                    and _as_utc(latest.timestamp) > failure_timestamp
                ):
                    logger.info(
                        f"Scheduler: Retry für Scan '{scan_slug}' entfällt: "
                        "ein neuerer Lauf ist vorhanden"
                    )
                    return

                jitter = random.randint(0, SCAN_RETRY_JITTER_SECONDS)
                wait_seconds = policy.delay_seconds + jitter
                retry_at = datetime.now(timezone.utc) + timedelta(
                    seconds=wait_seconds
                )
                next_regular = self._next_regular_run(scan_slug)
                if (
                    next_regular is not None
                    and _as_utc(next_regular) <= retry_at
                ):
                    logger.info(
                        f"Scheduler: Retry {retry_number}/{policy.count} für "
                        f"Scan '{scan_slug}' entfällt; regulärer Lauf um "
                        f"{_as_utc(next_regular).isoformat()} ist früher fällig"
                    )
                    return

                if not self._set_retry_info(
                    scan_slug,
                    sequence,
                    RetryInfo(
                        state="pending",
                        attempt=retry_number,
                        max_attempts=policy.count,
                        scheduled_at=retry_at,
                        reason=reason,
                    ),
                ):
                    return

                logger.warning(
                    f"Scheduler: Scan '{scan_slug}' wird wiederholt "
                    f"({retry_number}/{policy.count}) um {retry_at.isoformat()}; "
                    f"Grund: {reason}, Basiswartezeit: {policy.delay_seconds}s, "
                    f"Jitter: {jitter}s"
                )
                if await self._wait_for_retry(sequence, wait_seconds):
                    return
                if not self._sequence_is_current(scan_slug, sequence):
                    return
                if scanner_service.is_scan_running(scan_slug):
                    logger.info(
                        f"Scheduler: Retry für Scan '{scan_slug}' entfällt: "
                        "ein anderer Lauf ist aktiv"
                    )
                    return

                job = jobs_store.get_job(scan_slug)
                if job is None or not job["enabled"]:
                    logger.info(
                        f"Scheduler: Retry für Scan '{scan_slug}' entfällt: "
                        "Job wurde gelöscht oder deaktiviert"
                    )
                    return
                latest = storage.get_latest_result(scan_slug)
                if (
                    latest is not None
                    and _as_utc(latest.timestamp) > failure_timestamp
                ):
                    logger.info(
                        f"Scheduler: Retry für Scan '{scan_slug}' entfällt: "
                        "ein neuerer Lauf hat den Fehlerzustand abgelöst"
                    )
                    return

                current_config = jobs_store.to_scan_config(job)
                if not self._set_retry_info(
                    scan_slug,
                    sequence,
                    RetryInfo(
                        state="running",
                        attempt=retry_number,
                        max_attempts=policy.count,
                        reason=reason,
                    ),
                ):
                    return
        finally:
            self._finish_retry_sequence(scan_slug, sequence)
    
    def start(self) -> None:
        """Startet den Scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler gestartet")
        else:
            logger.warning("Scheduler läuft bereits")
    
    def stop(self) -> None:
        """Stoppt den Scheduler"""
        with self._retry_lock:
            retry_slugs = list(self._retry_sequences)
        for scan_slug in retry_slugs:
            self.cancel_retry_sequence(scan_slug, "Scheduler wird gestoppt")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler gestoppt")
        else:
            logger.warning("Scheduler läuft nicht")
    
    def get_job_info(self, scan_slug: str) -> Optional[Dict]:
        """
        Gibt Informationen über einen Job zurück
        
        Args:
            scan_slug: Slug des Scans
        
        Returns:
            Dictionary mit Job-Informationen oder None
        """
        # .get() statt "in"-Prüfung + Zugriff: /health läuft in einem
        # Worker-Thread und kann sonst genau zwischen beidem auf einen
        # gerade entfernten Job treffen (KeyError).
        job_id = self._job_ids.get(scan_slug)
        if job_id is None:
            return None

        job = self.scheduler.get_job(job_id)

        if not job:
            return None
        
        # next_run_time existiert erst, wenn der Scheduler gestartet ist
        next_run = getattr(job, "next_run_time", None)

        return {
            "job_id": job_id,
            "name": job.name,
            "next_run": next_run,
            "trigger": str(job.trigger)
        }

    def get_expected_interval_seconds(self, scan_slug: str) -> Optional[float]:
        """
        Ermittelt das erwartete Scan-Intervall eines Jobs in Sekunden.

        Wird für die Alters-Schwellwerte der PRTG-Sensoren gebraucht
        ("Scan ist überfällig"). Reihenfolge:
        1. Kurzform-Intervall aus der Job-Konfiguration ("30m", "6h", ...)
        2. Cron-Trigger: Differenz zweier aufeinanderfolgender Feuerzeiten
        3. None, wenn sich kein Intervall bestimmen lässt

        Args:
            scan_slug: Slug des Scans

        Returns:
            Intervall in Sekunden oder None
        """
        # 1. Kurzform direkt aus der Job-Konfiguration
        try:
            from app.services.jobs_store import jobs_store

            job = jobs_store.get_job(scan_slug)
            if job:
                delta = parse_interval_string(job["interval"])
                if delta is not None:
                    return delta.total_seconds()
        except Exception as e:
            logger.debug(f"Intervall aus Job-Konfiguration nicht ermittelbar: {e}")

        # 2. Cron: zwei aufeinanderfolgende Feuerzeiten differenzieren
        try:
            job_id = self._job_ids.get(scan_slug)
            if job_id:
                job = self.scheduler.get_job(job_id)
                if job is not None:
                    now = datetime.now(timezone.utc)
                    first = job.trigger.get_next_fire_time(None, now)
                    if first is not None:
                        second = job.trigger.get_next_fire_time(first, first)
                        if second is not None:
                            return (second - first).total_seconds()
        except Exception as e:
            logger.debug(f"Intervall aus Trigger nicht ermittelbar: {e}")

        return None


    def get_all_jobs(self) -> Dict[str, Dict]:
        """
        Gibt Informationen über alle Jobs zurück
        
        Returns:
            Dictionary mit Job-Informationen (Key: scan_slug)
        """
        jobs = {}
        # Über eine Kopie iterieren: /health liest aus einem Worker-Thread,
        # während der Event-Loop Jobs an-/abmelden kann (sonst
        # "dictionary changed size during iteration").
        for scan_slug in list(self._job_ids):
            job_info = self.get_job_info(scan_slug)
            if job_info:
                jobs[scan_slug] = job_info
        return jobs


# Globale Scheduler-Instanz
scheduler_service = SchedulerService()
