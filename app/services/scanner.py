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
        self._running_scans: dict[str, bool] = {}  # Track laufende Scans
        self._scan_status: dict[str, dict] = {}  # Intermediäre Status-Informationen für laufende Scans
    
    def is_scan_running(self, scan_name: str) -> bool:
        """Prüft ob ein Scan aktuell läuft"""
        return self._running_scans.get(scan_name, False)
    
    def get_scan_progress(self, scan_name: str) -> Optional[dict]:
        """
        Gibt die aktuellen intermediären Status-Informationen eines laufenden Scans zurück.
        
        Args:
            scan_name: Name des Scans
            
        Returns:
            Dict mit Status-Informationen oder None wenn Scan nicht läuft
        """
        return self._scan_status.get(scan_name)
    
    async def run_scan(self, scan_config: ScanTaskConfigYAML) -> ScanResult:
        """
        Führt einen Scan basierend auf der Konfiguration aus
        
        Args:
            scan_config: Scan-Konfiguration aus YAML
        
        Returns:
            ScanResult mit Timestamp
        """
        scan_name = scan_config.name
        start_time = datetime.now(timezone.utc)
        
        # Prüfe ob bereits ein Scan läuft
        if self.is_scan_running(scan_name):
            logger.warning(f"Scan '{scan_name}' läuft bereits")
            # Erstelle ein temporäres "running" Result (wird nicht gespeichert)
            return ScanResult(
                scan_name=scan_name,
                timestamp=datetime.now(timezone.utc),
                status="running",
                results=[]
            )
        
        # Markiere Scan als laufend und initialisiere Status
        self._running_scans[scan_name] = True
        self._scan_status[scan_name] = {
            "num_dir": 0,
            "num_file": 0,
            "total_size": 0,
            "waited": 0,
            "finished": False,
            "current_path": None
        }
        logger.info(f"=== Scan '{scan_name}' gestartet ===")
        logger.info(f"Scan '{scan_name}': Verbinde zu NAS {scan_config.nas.host}:{scan_config.nas.port}")
        
        # Erstelle initiales ScanResult mit Status "running"
        # WICHTIG: "running" Status wird NICHT gespeichert, nur in-memory gehalten
        timestamp = datetime.now(timezone.utc)
        scan_result = ScanResult(
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
                storage.add_result(scan_name, scan_result, scan_config.nas.host)
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
                    storage.add_result(scan_name, scan_result, scan_config.nas.host)
                    return scan_result
                
                logger.info(f"Scan '{scan_name}': {len(paths)} Pfad(e) zum Scannen gefunden: {paths}")
                
                # Führe Scans für alle Pfade aus
                result_items = []
                
                # Erstelle Callback für Status-Updates
                def update_scan_status(status_info: dict):
                    """Aktualisiert den intermediären Status des Scans"""
                    if scan_name in self._running_scans:
                        # Aktualisiere Status mit neuen Informationen
                        current_status = self._scan_status.get(scan_name, {})
                        current_status.update(status_info)
                        # Speichere auch den aktuellen Pfad
                        current_status["current_path"] = path
                        self._scan_status[scan_name] = current_status
                
                for idx, path in enumerate(paths, 1):
                    try:
                        logger.info(f"Scan '{scan_name}': [{idx}/{len(paths)}] Starte Scan von '{path}'")
                        path_start_time = datetime.now(timezone.utc)
                        
                        # Aktualisiere Status mit aktuellem Pfad
                        if scan_name in self._scan_status:
                            self._scan_status[scan_name]["current_path"] = path
                        
                        # Übergib Callback an get_dir_size_async
                        result = await api.get_dir_size_async(
                            path, 
                            max_wait=300,
                            status_callback=update_scan_status  # Callback für Status-Updates
                        )
                        path_duration = (datetime.now(timezone.utc) - path_start_time).total_seconds()
                        
                        if result is None:
                            logger.warning(f"Scan '{scan_name}': [{idx}/{len(paths)}] Scan von '{path}' fehlgeschlagen - keine Ergebnisse erhalten")
                            result_items.append(ScanResultItem(
                                folder_name=path,
                                success=False,
                                error="Scan fehlgeschlagen - keine Ergebnisse erhalten"
                            ))
                            continue
                        
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
            # Markiere Scan als beendet und entferne Status
            self._running_scans[scan_name] = False
            if scan_name in self._scan_status:
                del self._scan_status[scan_name]
        
        # Speichere nur abgeschlossene Scans (completed oder failed)
        # "running" Status wird nicht gespeichert
        if scan_result.status != "running":
            storage.add_result(scan_name, scan_result, scan_config.nas.host)
        
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
