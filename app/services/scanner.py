"""Scanner Service - Wrapper um explore_syno_api.py"""
import sys
import os
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from pathlib import Path

# Füge das Projekt-Root zum Python-Pfad hinzu, um explore_syno_api zu importieren
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from explore_syno_api import SynologyAPI
from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.models.config import ScanTaskConfigYAML
from app.services.storage import storage
import logging

logger = logging.getLogger(__name__)

# Aktiviere Logging für explore_syno_api
os.environ.setdefault('SYNO_ENABLE_LOGS', 'info')
explore_logger = logging.getLogger('explore_syno_api')
explore_logger.setLevel(logging.INFO)


class ScannerService:
    """Service zum Ausführen von Scans mit Timestamp-Integration"""
    
    def __init__(self):
        """Initialisiert den Scanner Service"""
        self._running_scans: dict[str, bool] = {}  # Track laufende Scans (Key: scan_slug)
        self._scan_status: dict[str, dict] = {}  # Intermediäre Status-Informationen für laufende Scans (Key: scan_slug)
        self._scan_finished_at: dict[str, datetime] = {}  # Timestamp wann Scan beendet wurde (für Grace Period, Key: scan_slug)
    
    def is_scan_running(self, scan_slug: str) -> bool:
        """
        Prüft ob ein Scan aktuell läuft oder kürzlich beendet wurde.
        
        Ein Scan gilt als "laufend" wenn:
        - Er aktiv läuft, ODER
        - Er innerhalb der letzten 5 Sekunden beendet wurde (Grace Period für Frontend)
        
        Args:
            scan_slug: Slug des Scans
        """
        if self._running_scans.get(scan_slug, False):
            return True
        
        # Prüfe ob Scan kürzlich beendet wurde (Grace Period: 5 Sekunden)
        if scan_slug in self._scan_finished_at:
            finished_at = self._scan_finished_at[scan_slug]
            time_since_finished = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if time_since_finished < 5:  # 5 Sekunden Grace Period
                return True
            else:
                # Grace Period abgelaufen, entferne Eintrag
                del self._scan_finished_at[scan_slug]
                if scan_slug in self._scan_status:
                    del self._scan_status[scan_slug]
        
        return False
    
    def get_scan_progress(self, scan_slug: str) -> Optional[dict]:
        """
        Gibt die aktuellen intermediären Status-Informationen eines laufenden Scans zurück.
        
        Args:
            scan_slug: Slug des Scans
            
        Returns:
            Dict mit Status-Informationen oder None wenn Scan nicht läuft
        """
        return self._scan_status.get(scan_slug)
    
    def _normalize_path(self, path: str) -> str:
        """
        Normalisiert einen Pfad für konsistenten Vergleich.
        
        Args:
            path: Pfad (kann mit oder ohne führenden Slash sein)
        
        Returns:
            Normalisierter Pfad (immer mit führendem Slash)
        """
        if not path:
            return ""
        # Stelle sicher, dass Pfad mit / beginnt
        normalized = path.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized
    
    def _aggregate_path_status(self, scan_slug: str) -> None:
        """
        Aggregiert die Status-Werte aller Pfade für einen Scan.
        
        Args:
            scan_slug: Slug des Scans
        """
        if scan_slug not in self._scan_status:
            return
        
        current_status = self._scan_status[scan_slug]
        
        # Initialisiere path_status falls nicht vorhanden
        if "path_status" not in current_status:
            current_status["path_status"] = {}
        
        # Aggregiere Werte aus allen Pfaden
        aggregated_num_dir = sum(
            path_stat.get("num_dir", 0) 
            for path_stat in current_status["path_status"].values()
        )
        aggregated_num_file = sum(
            path_stat.get("num_file", 0) 
            for path_stat in current_status["path_status"].values()
        )
        aggregated_total_size = sum(
            path_stat.get("total_size", 0) 
            for path_stat in current_status["path_status"].values()
        )
        
        # Verwende den maximalen waited-Wert (längster laufender Scan)
        max_waited = max(
            (path_stat.get("waited", 0) 
             for path_stat in current_status["path_status"].values()),
            default=0
        )
        
        # Prüfe ob alle erwarteten Pfade fertig sind
        # WICHTIG: Nur wenn alle erwarteten Pfade fertig sind, ist der Scan komplett
        expected_paths = current_status.get("expected_paths", [])
        if expected_paths:
            # Prüfe ob alle erwarteten Pfade in path_status sind und fertig
            # (expected_paths sind bereits normalisiert, path_status Keys auch)
            all_finished = all(
                current_status["path_status"].get(path, {}).get("finished", False)
                for path in expected_paths
            )
        else:
            # Fallback: Prüfe nur die Pfade, die bereits in path_status sind
            # (für Kompatibilität, falls expected_paths nicht gesetzt ist)
            all_finished = all(
                path_stat.get("finished", False) 
                for path_stat in current_status["path_status"].values()
            ) if current_status["path_status"] else False
        
        # Aktualisiere aggregierte Werte
        current_status["num_dir"] = aggregated_num_dir
        current_status["num_file"] = aggregated_num_file
        current_status["total_size"] = aggregated_total_size
        current_status["waited"] = max_waited
        current_status["finished"] = all_finished
    
    async def run_scan(self, scan_config: ScanTaskConfigYAML) -> ScanResult:
        """
        Führt einen Scan basierend auf der Konfiguration aus
        
        Args:
            scan_config: Scan-Konfiguration aus YAML
        
        Returns:
            ScanResult mit Timestamp
        """
        scan_slug = scan_config.slug
        scan_name = scan_config.name
        start_time = datetime.now(timezone.utc)
        
        # Prüfe ob bereits ein Scan läuft
        if self.is_scan_running(scan_slug):
            logger.warning(f"Scan '{scan_name}' läuft bereits")
            # Erstelle ein temporäres "running" Result (wird nicht gespeichert)
            return ScanResult(
                scan_slug=scan_slug,
                scan_name=scan_name,
                timestamp=datetime.now(timezone.utc),
                status="running",
                results=[]
            )
        
        # Markiere Scan als laufend und initialisiere Status
        # Entferne alte Grace-Period-Daten falls vorhanden
        if scan_slug in self._scan_finished_at:
            del self._scan_finished_at[scan_slug]
        
        self._running_scans[scan_slug] = True
        self._scan_status[scan_slug] = {
            "num_dir": 0,
            "num_file": 0,
            "total_size": 0,
            "waited": 0,
            "finished": False,
            "current_path": None,
            "path_status": {}  # Status pro Pfad für Aggregation
        }
        logger.info(f"=== Scan '{scan_name}' gestartet ===")
        logger.info(f"Scan '{scan_name}': Verbinde zu NAS {scan_config.nas.host}:{scan_config.nas.port}")
        
        # Erstelle initiales ScanResult mit Status "running"
        # WICHTIG: "running" Status wird NICHT gespeichert, nur in-memory gehalten
        timestamp = datetime.now(timezone.utc)
        scan_result = ScanResult(
            scan_slug=scan_slug,
            scan_name=scan_name,
            timestamp=timestamp,
            status="running",
            results=[]
        )
        
        # NICHT speichern - "running" Status ist nur temporär
        
        try:
            # Initialisiere API
            api = SynologyAPI(
                host=scan_config.nas.host,
                port=scan_config.nas.port,
                use_https=scan_config.nas.use_https,
                output_json=True,  # Unterdrücke Print-Ausgaben
                verify_ssl=scan_config.nas.verify_ssl
            )
            
            # Login - in Thread-Pool auslagern, um Event Loop nicht zu blockieren
            logger.info(f"Scan '{scan_name}': Versuche Login bei {scan_config.nas.host}...")
            login_success = await asyncio.to_thread(
                api.login, 
                scan_config.nas.username, 
                scan_config.nas.password
            )
            if not login_success:
                error_msg = "Login fehlgeschlagen"
                logger.error(f"Scan '{scan_name}': {error_msg}")
                scan_result.status = "failed"
                scan_result.error = error_msg
                scan_result.timestamp = datetime.now(timezone.utc)
                # Speichere fehlgeschlagenen Scan
                storage.add_result(scan_slug, scan_name, scan_result, scan_config.nas.host)
                return scan_result
            
            logger.info(f"Scan '{scan_name}': Login erfolgreich")
            
            try:
                # Bestimme alle zu scannenden Pfade
                paths = self._determine_paths(scan_config)
                
                if not paths:
                    error_msg = "Kein gültiger Pfad in Konfiguration gefunden"
                    logger.error(f"Scan '{scan_name}': {error_msg}")
                    scan_result.status = "failed"
                    scan_result.error = error_msg
                    scan_result.timestamp = datetime.now(timezone.utc)
                    # Speichere fehlgeschlagenen Scan
                    storage.add_result(scan_slug, scan_name, scan_result, scan_config.nas.host)
                    return scan_result
                
                logger.info(f"Scan '{scan_name}': {len(paths)} Pfad(e) zum Scannen gefunden: {paths}")
                
                # Speichere erwartete Pfade im Status für korrekte finished-Prüfung (normalisiert)
                if scan_slug in self._scan_status:
                    self._scan_status[scan_slug]["expected_paths"] = [
                        self._normalize_path(path) for path in paths
                    ]
                
                # Führe Scans für alle Pfade aus
                result_items = []
                
                # Erstelle Callback für Status-Updates für einen spezifischen Pfad
                def create_path_status_callback(path_to_scan: str):
                    """Erstellt einen Callback für Status-Updates für einen spezifischen Pfad"""
                    def update_scan_status(status_info: dict):
                        """Aktualisiert den intermediären Status des Scans für einen spezifischen Pfad"""
                        if scan_slug in self._running_scans:
                            current_status = self._scan_status.get(scan_slug, {})
                            
                            # Initialisiere path_status falls nicht vorhanden
                            if "path_status" not in current_status:
                                current_status["path_status"] = {}
                            
                            # Speichere Status für diesen spezifischen Pfad (normalisiert)
                            normalized_path = self._normalize_path(path_to_scan)
                            current_status["path_status"][normalized_path] = {
                                "num_dir": status_info.get("num_dir", 0),
                                "num_file": status_info.get("num_file", 0),
                                "total_size": status_info.get("total_size", 0),
                                "waited": status_info.get("waited", 0),
                                "finished": status_info.get("finished", False)
                            }
                            
                            # Aggregiere Werte aus allen Pfaden
                            self._aggregate_path_status(scan_slug)
                            
                            # Aktualisiere current_path
                            current_status = self._scan_status.get(scan_slug, {})
                            current_status["current_path"] = path_to_scan
                            self._scan_status[scan_slug] = current_status
                    
                    return update_scan_status
                
                for idx, path in enumerate(paths, 1):
                    try:
                        logger.info(f"Scan '{scan_name}': [{idx}/{len(paths)}] Starte Scan von '{path}'")
                        path_start_time = datetime.now(timezone.utc)
                        
                        # Erstelle Callback für diesen spezifischen Pfad
                        path_status_callback = create_path_status_callback(path)
                        
                        # Übergib Callback an get_dir_size_async
                        result = await api.get_dir_size_async(
                            path, 
                            max_wait=300,
                            status_callback=path_status_callback  # Callback für Status-Updates
                        )
                        path_duration = (datetime.now(timezone.utc) - path_start_time).total_seconds()
                        
                        if result is None:
                            logger.warning(f"Scan '{scan_name}': [{idx}/{len(paths)}] Scan von '{path}' fehlgeschlagen - keine Ergebnisse erhalten")
                            # Markiere Pfad als fertig (fehlgeschlagen) im Status (normalisiert)
                            if scan_slug in self._scan_status:
                                current_status = self._scan_status.get(scan_slug, {})
                                if "path_status" not in current_status:
                                    current_status["path_status"] = {}
                                normalized_path = self._normalize_path(path)
                                current_status["path_status"][normalized_path] = {
                                    "num_dir": 0,
                                    "num_file": 0,
                                    "total_size": 0,
                                    "waited": 0,
                                    "finished": True
                                }
                                self._scan_status[scan_slug] = current_status
                                # Re-aggregiere Werte
                                self._aggregate_path_status(scan_slug)
                            
                            result_items.append(ScanResultItem(
                                folder_name=path,
                                success=False,
                                error="Scan fehlgeschlagen - keine Ergebnisse erhalten"
                            ))
                            continue
                        
                        # Aktualisiere finalen Status für diesen Pfad mit den Ergebnissen (normalisiert)
                        if scan_slug in self._scan_status:
                            current_status = self._scan_status.get(scan_slug, {})
                            if "path_status" not in current_status:
                                current_status["path_status"] = {}
                            normalized_path = self._normalize_path(path)
                            current_status["path_status"][normalized_path] = {
                                "num_dir": result.get('num_dir', 0),
                                "num_file": result.get('num_file', 0),
                                "total_size": result.get('total_size', 0),
                                "waited": 0,
                                "finished": True
                            }
                            self._scan_status[scan_slug] = current_status
                            # Re-aggregiere Werte
                            self._aggregate_path_status(scan_slug)
                        
                        # Konvertiere Ergebnis in ScanResultItem
                        size_info = api._format_size_with_unit(result['total_size'])
                        
                        result_item = ScanResultItem(
                            folder_name=path,
                            success=True,
                            num_dir=result.get('num_dir', 0),
                            num_file=result.get('num_file', 0),
                            total_size=TotalSize(
                                bytes=size_info['size_bytes'],
                                formatted=size_info['size_formatted'],
                                unit=size_info['unit']
                            ),
                            elapsed_time_ms=int(round(result.get('elapsed_time', 0) * 1000))
                        )
                        result_items.append(result_item)
                        logger.info(
                            f"Scan '{scan_name}': [{idx}/{len(paths)}] Erfolgreich abgeschlossen für '{path}' - "
                            f"Größe: {size_info['size_formatted']} {size_info['unit']}, "
                            f"Dauer: {path_duration:.1f}s, "
                            f"Ordner: {result.get('num_dir', 0)}, Dateien: {result.get('num_file', 0)}"
                        )
                        
                    except Exception as e:
                        logger.exception(f"Scan '{scan_name}': [{idx}/{len(paths)}] Fehler beim Scannen von '{path}': {str(e)}")
                        result_items.append(ScanResultItem(
                            folder_name=path,
                            success=False,
                            error=f"Fehler beim Scannen: {str(e)}"
                        ))
                
                # Aktualisiere ScanResult mit allen Ergebnissen
                scan_result.results = result_items
                scan_result.timestamp = datetime.now(timezone.utc)  # Aktualisiere Timestamp
                
                # Stelle sicher, dass finished-Flag gesetzt ist, wenn alle Pfade gescannt wurden
                if scan_slug in self._scan_status:
                    # Alle Pfade sind jetzt gescannt, setze finished auf True
                    self._scan_status[scan_slug]["finished"] = True
                    # Re-aggregiere um sicherzustellen, dass alles korrekt ist
                    self._aggregate_path_status(scan_slug)
                
                total_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                successful = sum(1 for r in result_items if r.success)
                
                # Prüfe ob mindestens ein erfolgreiches Ergebnis vorhanden ist
                if successful == 0:
                    # Keine erfolgreichen Ergebnisse - markiere als fehlgeschlagen
                    scan_result.status = "failed"
                    scan_result.error = "Alle Pfade fehlgeschlagen - keine erfolgreichen Ergebnisse"
                    logger.warning(
                        f"Scan '{scan_name}': === Fehlgeschlagen === "
                        f"Keine erfolgreichen Ergebnisse ({len(result_items)} Pfad(e) fehlgeschlagen), "
                        f"Gesamtdauer: {total_duration:.1f}s"
                    )
                else:
                    scan_result.status = "completed"
                    logger.info(
                        f"Scan '{scan_name}': === Abgeschlossen === "
                        f"{successful}/{len(result_items)} Pfad(e) erfolgreich, "
                        f"Gesamtdauer: {total_duration:.1f}s"
                    )
                
            finally:
                # Logout - in Thread-Pool auslagern, um Event Loop nicht zu blockieren
                logger.info(f"Scan '{scan_name}': Logout von NAS...")
                await asyncio.to_thread(api.logout)
                await asyncio.to_thread(api.cleanup_tasks, ignore_errors=True)
                # WICHTIG: Async Session schließen, um "Unclosed client session" Fehler zu vermeiden
                await api.close_async_session()
        
        except Exception as e:
            error_msg = f"Unerwarteter Fehler: {str(e)}"
            logger.exception(f"Scan '{scan_name}': {error_msg}")
            scan_result.status = "failed"
            scan_result.error = error_msg
            scan_result.timestamp = datetime.utcnow()  # Aktualisiere Timestamp
        
        finally:
            # Markiere Scan als beendet, aber behalte Status für Grace Period
            self._running_scans[scan_slug] = False
            # Speichere Timestamp für Grace Period (5 Sekunden)
            if scan_slug in self._scan_status:
                self._scan_finished_at[scan_slug] = datetime.now(timezone.utc)
                # Status bleibt erhalten für Grace Period
        
        # Speichere nur abgeschlossene Scans (completed oder failed)
        # "running" Status wird nicht gespeichert
        if scan_result.status != "running":
            storage.add_result(scan_slug, scan_name, scan_result, scan_config.nas.host)
        
        return scan_result
    
    def _determine_paths(self, scan_config: ScanTaskConfigYAML) -> List[str]:
        """
        Bestimmt alle zu scannenden Pfade aus der Konfiguration
        
        Args:
            scan_config: Scan-Konfiguration
        
        Returns:
            Liste von Pfaden als Strings
        
        Mögliche Kombinationen:
        - paths: scannt alle Pfade in der Liste
        - shares (ohne folders): scannt alle shares
        - shares + folders: scannt alle Kombinationen (share/folder1, share/folder2, ...)
          WICHTIG: Bei folders darf nur 1 Share angegeben werden!
        - shares + paths: scannt alle shares UND alle paths
        - shares + folders + paths: scannt share/folder Kombinationen UND alle paths
          WICHTIG: Bei folders darf nur 1 Share angegeben werden!
        """
        paths = []
        
        # Pfade hinzufügen (wenn vorhanden)
        if scan_config.paths:
            for path in scan_config.paths:
                normalized_path = path
                if not normalized_path.startswith("/"):
                    normalized_path = f"/{normalized_path}"
                paths.append(normalized_path)
        
        # Share-basierte Pfade hinzufügen (wenn vorhanden)
        if scan_config.shares:
            shares = scan_config.shares
            
            if scan_config.folders:
                # Shares + Folders: Alle Kombinationen
                # Validierung stellt sicher, dass nur 1 Share vorhanden ist
                folders = scan_config.folders
                for share in shares:
                    for folder in folders:
                        paths.append(f"/{share}/{folder}")
            else:
                # Nur Shares: scannt alle shares
                for share in shares:
                    paths.append(f"/{share}")
        
        return paths


# Globale Scanner-Instanz
scanner_service = ScannerService()
