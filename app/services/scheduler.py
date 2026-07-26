"""Scheduler Service - APScheduler Integration"""
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Union
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.services.scanner import scanner_service
from app.models.config import ScanTaskConfigYAML

logger = logging.getLogger(__name__)


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
        # Fingerabdruck der zuletzt eingeplanten Konfiguration je Slug.
        # Damit erkennt der Resync, ob sich ein Job wirklich geändert hat -
        # sonst wurde jeder bestehende Job neu eingeplant und das Intervall
        # begann von vorn (ein häufiger Reload konnte Läufe dauerhaft
        # verschieben).
        self._job_signatures: Dict[str, str] = {}

    @staticmethod
    def _job_signature(scan_config: ScanTaskConfigYAML) -> str:
        """Fingerabdruck aller Felder, die den eingeplanten Lauf bestimmen"""
        payload = json.dumps(
            {
                "name": scan_config.name,
                "interval": scan_config.interval,
                "shares": scan_config.shares,
                "folders": scan_config.folders,
                "paths": scan_config.paths,
                "enabled": scan_config.enabled,
                "nas": {
                    "host": scan_config.nas.host,
                    "port": scan_config.nas.port,
                    "use_https": scan_config.nas.use_https,
                    "verify_ssl": scan_config.nas.verify_ssl,
                    "username": scan_config.nas.username,
                    # Die Zugangsdaten stecken im eingeplanten Job-Argument,
                    # ein Passwortwechsel muss also neu einplanen. Nur als
                    # Hash, damit das Klartextpasswort nirgends liegen bleibt.
                    "password": hashlib.sha256(
                        (scan_config.nas.password or "").encode("utf-8")
                    ).hexdigest(),
                },
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    
    def load_and_schedule(self, config_path: Optional[str] = None) -> None:
        """
        Lädt alle aktivierten Scan-Jobs aus der Datenbank und plant sie ein.

        (Jobs leben seit der Frontend-Verwaltung in der SQLite-DB;
        config.yaml wird nur noch einmalig beim ersten Start importiert.)
        """
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
            self._job_signatures[scan_config.slug] = self._job_signature(scan_config)

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
        job_id = self._job_ids.get(scan_slug)
        if job_id is None:
            return False

        try:
            self.scheduler.remove_job(job_id)
            self._job_ids.pop(scan_slug, None)
            self._job_signatures.pop(scan_slug, None)
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
        job_start_time = datetime.now(timezone.utc)
        logger.info(f"=== Scheduler: Starte geplanten Scan '{scan_config.name}' ===")
        logger.info(f"Job '{scan_config.name}': Konfiguration - NAS: {scan_config.nas.host}, Interval: {scan_config.interval}")
        
        try:
            result = await scanner_service.run_scan(scan_config)
            job_duration = (datetime.now(timezone.utc) - job_start_time).total_seconds()
            
            if result.status == "completed":
                logger.info(
                    f"=== Scheduler: Scan '{scan_config.name}' erfolgreich abgeschlossen === "
                    f"Status: {result.status}, Dauer: {job_duration:.1f}s, "
                    f"Ergebnisse: {len(result.results)} Pfad(e)"
                )
            elif result.status == "failed":
                logger.error(
                    f"=== Scheduler: Scan '{scan_config.name}' fehlgeschlagen === "
                    f"Status: {result.status}, Dauer: {job_duration:.1f}s, "
                    f"Fehler: {result.error if result.error else 'Unbekannter Fehler'}"
                )
            else:
                logger.warning(
                    f"=== Scheduler: Scan '{scan_config.name}' mit Status '{result.status}' beendet === "
                    f"Dauer: {job_duration:.1f}s"
                )
        except Exception as e:
            job_duration = (datetime.now(timezone.utc) - job_start_time).total_seconds()
            logger.exception(
                f"=== Scheduler: Fehler beim Ausführen des Scans '{scan_config.name}' === "
                f"Dauer: {job_duration:.1f}s, Fehler: {e}"
            )
    
    def start(self) -> None:
        """Startet den Scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler gestartet")
        else:
            logger.warning("Scheduler läuft bereits")
    
    def stop(self) -> None:
        """Stoppt den Scheduler"""
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

    def resync_from_db(self) -> Dict[str, any]:
        """
        Synchronisiert die Scheduler-Jobs mit dem aktuellen Stand der Datenbank.

        Entfernt Jobs, die es nicht mehr gibt oder die deaktiviert wurden,
        und fügt neue/aktivierte Jobs hinzu. Bestehende Jobs werden nur dann
        neu eingeplant, wenn sich ihre Konfiguration tatsächlich geändert hat.

        Wichtig: Ein Neuplanen setzt bei Intervall-Triggern den Zähler zurück.
        Würde hier jeder bestehende Job angefasst, verschöbe jeder Aufruf den
        nächsten Lauf um ein volles Intervall - bei regelmässigem Reload liefe
        ein Job nie.

        Returns:
            Dictionary mit Informationen über die Synchronisierung
        """
        try:
            from app.services.jobs_store import jobs_store

            jobs = jobs_store.list_jobs()
            old_scan_slugs = set(self._job_ids.keys())
            enabled_jobs = {job["slug"]: job for job in jobs if job["enabled"]}

            # Entferne Jobs, die nicht mehr existieren oder deaktiviert sind
            removed_scans = []
            for scan_slug in list(old_scan_slugs):
                if scan_slug not in enabled_jobs:
                    if self.remove_scan_job(scan_slug):
                        removed_scans.append(scan_slug)

            # Füge neue hinzu bzw. plane bestehende neu ein
            added_scans = []
            updated_scans = []
            for slug, job in enabled_jobs.items():
                try:
                    scan_config = jobs_store.to_scan_config(job)
                except Exception as e:
                    logger.error(f"Job '{slug}' konnte nicht geladen werden: {e}")
                    continue
                if slug in old_scan_slugs:
                    # Unveränderte Jobs in Ruhe lassen, sonst beginnt ihr
                    # Intervall bei jedem Resync von vorn.
                    if self._job_signatures.get(slug) == self._job_signature(scan_config):
                        continue
                    self.remove_scan_job(slug)
                    self.add_scan_job(scan_config)
                    updated_scans.append(job["name"])
                else:
                    self.add_scan_job(scan_config)
                    added_scans.append(job["name"])

            result = {
                "success": True,
                "message": "Scheduler erfolgreich aus der Datenbank synchronisiert",
                "added_scans": added_scans,
                "updated_scans": updated_scans,
                "removed_scans": removed_scans,
                "total_scans": len(jobs)
            }

            logger.info(f"Scheduler-Resync abgeschlossen: {result}")
            return result

        except Exception as e:
            logger.error(f"Fehler beim Synchronisieren aus der Datenbank: {e}")
            return {
                "success": False,
                "message": f"Fehler beim Synchronisieren: {str(e)}",
                "error": str(e)
            }

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
