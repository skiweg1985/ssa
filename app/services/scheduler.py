"""Scheduler Service - APScheduler Integration"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Union
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.config.loader import load_config, get_scan_config
from app.services.scanner import scanner_service
from app.models.config import ConfigYAML, ScanTaskConfigYAML

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
    
    # Konvertiere in timedelta
    if unit == 's':
        return timedelta(seconds=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'd':
        return timedelta(days=value)
    
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
        self.config: Optional[ConfigYAML] = None
        self._job_ids: Dict[str, str] = {}  # Mapping von scan_slug zu job_id
    
    def load_and_schedule(self, config_path: Optional[str] = None) -> None:
        """
        Lädt die Konfiguration und erstellt Jobs für alle aktivierten Scans
        
        Args:
            config_path: Pfad zur config.yaml Datei
        """
        try:
            self.config = load_config(config_path)
            logger.info(f"Konfiguration geladen: {len(self.config.scans)} Scan-Tasks gefunden")
            
            for scan_config in self.config.scans:
                if scan_config.enabled:
                    self.add_scan_job(scan_config)
                else:
                    logger.info(f"Scan '{scan_config.name}' ist deaktiviert, überspringe")
            
            # Richte automatisches Neuladen der Config ein (alle 5 Minuten)
            self._setup_config_reload_job()
        
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfiguration: {e}")
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
        if scan_slug not in self._job_ids:
            return False
        
        job_id = self._job_ids[scan_slug]
        try:
            self.scheduler.remove_job(job_id)
            del self._job_ids[scan_slug]
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
        if scan_slug not in self._job_ids:
            return None
        
        job_id = self._job_ids[scan_slug]
        job = self.scheduler.get_job(job_id)
        
        if not job:
            return None
        
        return {
            "job_id": job_id,
            "name": job.name,
            "next_run": job.next_run_time,
            "trigger": str(job.trigger)
        }
    
    def reload_config(self, config_path: Optional[str] = None) -> Dict[str, any]:
        """
        Lädt die Konfiguration neu und aktualisiert alle Jobs
        
        Args:
            config_path: Pfad zur config.yaml Datei
        
        Returns:
            Dictionary mit Informationen über das Neuladen
        """
        try:
            old_scan_slugs = set(self._job_ids.keys()) if self.config else set()
            
            # Lade neue Konfiguration
            new_config = load_config(config_path)
            logger.info(f"Konfiguration neu geladen: {len(new_config.scans)} Scan-Tasks gefunden")
            
            new_scan_slugs = {scan.slug for scan in new_config.scans}
            
            # Entferne Jobs für Scans, die nicht mehr in der Config sind
            removed_scans = []
            for scan_slug in old_scan_slugs:
                if scan_slug not in new_scan_slugs:
                    if self.remove_scan_job(scan_slug):
                        removed_scans.append(scan_slug)
            
            # Aktualisiere oder füge neue Jobs hinzu
            added_scans = []
            updated_scans = []
            for scan_config in new_config.scans:
                if scan_config.enabled:
                    if scan_config.slug in old_scan_slugs:
                        # Job existiert bereits, prüfe ob sich die Konfiguration geändert hat
                        old_scan_config = None
                        if self.config:
                            for old_scan in self.config.scans:
                                if old_scan.slug == scan_config.slug:
                                    old_scan_config = old_scan
                                    break
                        
                        # Vergleiche Konfigurationen, um zu sehen, ob sich etwas geändert hat
                        config_changed = False
                        if old_scan_config:
                            # Vergleiche relevante Felder (shares, folders, paths, interval, nas)
                            if (old_scan_config.shares != scan_config.shares or
                                old_scan_config.folders != scan_config.folders or
                                old_scan_config.paths != scan_config.paths or
                                old_scan_config.interval != scan_config.interval or
                                old_scan_config.nas.host != scan_config.nas.host or
                                old_scan_config.nas.port != scan_config.nas.port):
                                config_changed = True
                                logger.info(
                                    f"Konfiguration für Scan '{scan_config.name}' hat sich geändert. "
                                    f"Alt: shares={old_scan_config.shares}, folders={old_scan_config.folders}, paths={old_scan_config.paths} | "
                                    f"Neu: shares={scan_config.shares}, folders={scan_config.folders}, paths={scan_config.paths}"
                                )
                        else:
                            config_changed = True
                        
                        # Finde alte Scan-Config für Vergleich
                        old_scan_config = None
                        if self.config:
                            for old_scan in self.config.scans:
                                if old_scan.slug == scan_config.slug:
                                    old_scan_config = old_scan
                                    break
                        
                        if config_changed:
                            # Job existiert bereits, aktualisiere ihn
                            logger.info(f"Konfiguration für Scan '{scan_config.name}' hat sich geändert, aktualisiere Job...")
                            self.remove_scan_job(scan_config.slug)
                            self.add_scan_job(scan_config)
                            updated_scans.append(scan_config.name)
                        else:
                            logger.debug(f"Konfiguration für Scan '{scan_config.name}' unverändert, überspringe Update")
                    else:
                        # Neuer Job
                        logger.info(f"Neuer Scan '{scan_config.name}' gefunden, füge Job hinzu...")
                        self.add_scan_job(scan_config)
                        added_scans.append(scan_config.name)
                else:
                    # Scan ist deaktiviert, entferne Job falls vorhanden
                    if scan_config.slug in old_scan_slugs:
                        self.remove_scan_job(scan_config.slug)
                        removed_scans.append(scan_config.name)
            
            self.config = new_config
            
            result = {
                "success": True,
                "message": "Konfiguration erfolgreich neu geladen",
                "added_scans": added_scans,
                "updated_scans": updated_scans,
                "removed_scans": removed_scans,
                "total_scans": len(new_config.scans)
            }
            
            logger.info(f"Config-Reload abgeschlossen: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Fehler beim Neuladen der Konfiguration: {e}")
            return {
                "success": False,
                "message": f"Fehler beim Neuladen: {str(e)}",
                "error": str(e)
            }
    
    def _setup_config_reload_job(self) -> None:
        """
        Richtet einen periodischen Job ein, der die Konfiguration automatisch neu lädt
        (alle 5 Minuten)
        """
        try:
            # Entferne existierenden Config-Reload-Job falls vorhanden
            if self.scheduler.get_job("config_reload"):
                self.scheduler.remove_job("config_reload")
            
            # Füge neuen Job hinzu (alle 5 Minuten)
            self.scheduler.add_job(
                func=self._reload_config_job,
                trigger=IntervalTrigger(minutes=5),
                id="config_reload",
                name="Config Auto-Reload",
                replace_existing=True
            )
            logger.info("Automatisches Config-Reload eingerichtet (alle 5 Minuten)")
        except Exception as e:
            logger.error(f"Fehler beim Einrichten des Config-Reload-Jobs: {e}")
    
    async def _reload_config_job(self) -> None:
        """
        Wird periodisch vom Scheduler aufgerufen, um die Config neu zu laden
        """
        logger.info("Automatisches Neuladen der Konfiguration...")
        result = self.reload_config()
        if result["success"]:
            logger.info(f"Automatisches Config-Reload erfolgreich: {result['message']}")
        else:
            logger.warning(f"Automatisches Config-Reload fehlgeschlagen: {result['message']}")
    
    def get_all_jobs(self) -> Dict[str, Dict]:
        """
        Gibt Informationen über alle Jobs zurück
        
        Returns:
            Dictionary mit Job-Informationen (Key: scan_slug)
        """
        jobs = {}
        for scan_slug, job_id in self._job_ids.items():
            job_info = self.get_job_info(scan_slug)
            if job_info:
                jobs[scan_slug] = job_info
        return jobs


# Globale Scheduler-Instanz
scheduler_service = SchedulerService()
