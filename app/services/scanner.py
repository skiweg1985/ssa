"""Scanner Service - Wrapper um explore_syno_api.py"""
import sys
import os
import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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


# Zeitfenster, in dem ein beendeter Scan weiterhin als "laufend" gilt
# (damit das Frontend den Abschluss noch mitbekommt)
GRACE_PERIOD_SECONDS = 5

# Timeout je Pfad. Begrenzt einen einzelnen hängenden Pfad und ist die Basis
# für die Hängen-Schwelle in app/services/monitoring.py.
PATH_MAX_WAIT_SECONDS = 300


class ScannerService:
    """Service zum Ausführen von Scans mit Timestamp-Integration"""

    def __init__(self):
        """Initialisiert den Scanner Service"""
        self._running_scans: dict[str, bool] = {}  # Track laufende Scans (Key: scan_slug)
        self._scan_status: dict[str, dict] = {}  # Intermediäre Status-Informationen für laufende Scans (Key: scan_slug)
        self._scan_finished_at: dict[str, datetime] = {}  # Timestamp wann Scan beendet wurde (für Grace Period, Key: scan_slug)
        # Startzeitpunkt des laufenden Scans. BEWUSST nicht in _scan_status,
        # denn dessen Inhalt geht 1:1 in die Antwort von /progress - ein neues
        # Feld dort wäre eine stille Schema-Änderung.
        self._scan_started_at: dict[str, datetime] = {}
        # Abbruchwunsch. Scans laufen als FastAPI-BackgroundTask bzw. als
        # Scheduler-Job, es gibt also kein Task-Handle zum Cancellen - der
        # Abbruch ist kooperativ: der Scan-Lauf prüft dieses Flag.
        self._cancel_requested: dict[str, bool] = {}
        # WICHTIG: Der Scan-Zustand wird aus mehreren Threads gelesen und
        # geschrieben - der Scan selbst läuft im Event-Loop, /health wird per
        # asyncio.to_thread in einem Worker-Thread ausgeführt. Ohne Lock kann
        # ein lesender Monitoring-Aufruf zwischen Prüfung und Zugriff auf ein
        # gerade gelöschtes Dict-Element laufen (KeyError -> der Client bekommt
        # einen Fehler statt der letzten Werte). RLock, weil die Helfer sich
        # gegenseitig aufrufen.
        self._state_lock = threading.RLock()

    def is_scan_running(self, scan_slug: str) -> bool:
        """
        Prüft ob ein Scan aktuell läuft oder kürzlich beendet wurde.

        Ein Scan gilt als "laufend" wenn:
        - Er aktiv läuft, ODER
        - Er innerhalb der Grace Period beendet wurde (für das Frontend)

        Args:
            scan_slug: Slug des Scans
        """
        with self._state_lock:
            if self._running_scans.get(scan_slug, False):
                return True

            # Prüfe ob Scan kürzlich beendet wurde (Grace Period)
            finished_at = self._scan_finished_at.get(scan_slug)
            if finished_at is None:
                return False

            time_since_finished = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if time_since_finished < GRACE_PERIOD_SECONDS:
                return True

            # Grace Period abgelaufen, entferne Einträge
            self._scan_finished_at.pop(scan_slug, None)
            self._scan_status.pop(scan_slug, None)
            return False

    def get_scan_progress(self, scan_slug: str) -> Optional[dict]:
        """
        Gibt die aktuellen intermediären Status-Informationen eines laufenden Scans zurück.

        Args:
            scan_slug: Slug des Scans

        Returns:
            Kopie des Status-Dicts oder None wenn Scan nicht läuft
        """
        with self._state_lock:
            status = self._scan_status.get(scan_slug)
            if status is None:
                return None
            # Kopie (inkl. path_status), damit Aufrufer über einem stabilen
            # Stand arbeiten, während der laufende Scan weiter schreibt.
            snapshot = dict(status)
            snapshot["path_status"] = {
                path: dict(values)
                for path, values in status.get("path_status", {}).items()
            }
            return snapshot

    def _try_start_scan(self, scan_slug: str) -> bool:
        """
        Markiert einen Scan atomar als laufend.

        Args:
            scan_slug: Slug des Scans

        Returns:
            False wenn bereits ein Lauf aktiv ist (dann wurde nichts verändert)
        """
        with self._state_lock:
            if self.is_scan_running(scan_slug):
                return False
            # Alte Grace-Period-Daten des Vorlaufs verwerfen
            self._scan_finished_at.pop(scan_slug, None)
            # Ein Abbruchwunsch aus einem früheren Lauf darf den neuen nicht
            # sofort wieder beenden.
            self._cancel_requested.pop(scan_slug, None)
            self._running_scans[scan_slug] = True
            self._scan_started_at[scan_slug] = datetime.now(timezone.utc)
            self._scan_status[scan_slug] = {
                "num_dir": 0,
                "num_file": 0,
                "total_size": 0,
                "waited": 0,
                "finished": False,
                "current_path": None,
                "path_status": {},  # Status pro Pfad für Aggregation
            }
            return True

    def _finish_scan(self, scan_slug: str) -> None:
        """Markiert einen Scan als beendet, behält den Status für die Grace Period"""
        with self._state_lock:
            # Schluessel entfernen statt auf False setzen: is_scan_running()
            # liest ohnehin mit .get(slug, False), und ein liegengebliebener
            # False-Eintrag pro jemals gelaufenem Slug waechst unbegrenzt an
            # (auch fuer laengst geloeschte Jobs).
            self._running_scans.pop(scan_slug, None)
            self._scan_started_at.pop(scan_slug, None)
            self._cancel_requested.pop(scan_slug, None)
            if scan_slug in self._scan_status:
                self._scan_finished_at[scan_slug] = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Laufzeit und Abbruch
    # ------------------------------------------------------------------

    def get_scan_started_at(self, scan_slug: str) -> Optional[datetime]:
        """Startzeitpunkt des laufenden Scans, None wenn keiner läuft"""
        with self._state_lock:
            return self._scan_started_at.get(scan_slug)

    def request_cancel(self, scan_slug: str) -> bool:
        """
        Bittet einen laufenden Scan, sich zu beenden.

        Der Abbruch ist kooperativ: der Lauf prüft das Flag zwischen den
        Pfaden und innerhalb der Polling-Schleife der Größenabfrage. Die
        Rückgabe sagt also nur, dass der Wunsch hinterlegt wurde - nicht,
        dass der Scan schon beendet ist.

        Returns:
            False wenn gerade kein Lauf aktiv ist (dann wurde nichts hinterlegt)
        """
        with self._state_lock:
            # Auf _running_scans prüfen, nicht auf is_scan_running(): während
            # der Grace Period ist der Lauf längst vorbei, ein Abbruchwunsch
            # würde nur den nächsten Lauf belasten.
            if not self._running_scans.get(scan_slug, False):
                return False
            self._cancel_requested[scan_slug] = True
            return True

    def is_cancel_requested(self, scan_slug: str) -> bool:
        """Ob für diesen Scan ein Abbruch angefordert wurde"""
        with self._state_lock:
            return self._cancel_requested.get(scan_slug, False)

    def _persist_result(
        self, scan_slug: str, scan_name: str, scan_result: "ScanResult", nas_host: str
    ) -> bool:
        """
        Speichert ein Scan-Ergebnis - aber nur, wenn es den Job noch gibt.

        Wird ein Job gelöscht, während sein Scan läuft, endet der Lauf trotzdem
        regulär und schrieb bisher sein Ergebnis weg. Die Zeilen gehören dann zu
        keinem Job mehr: über die API sind sie nicht mehr erreichbar (jeder
        Endpunkt prüft zuerst die Job-Existenz) und sie überleben sogar ein
        ausdrückliches delete_history=true, weil der Scan nach dem Löschen
        schreibt.

        Returns:
            True, wenn gespeichert wurde
        """
        from app.services.jobs_store import jobs_store

        try:
            job_exists = jobs_store.get_job(scan_slug) is not None
        except Exception as e:
            # Store nicht erreichbar: im Zweifel speichern - ein verworfenes
            # Ergebnis wäre schlimmer als eine verwaiste Zeile.
            logger.warning(
                f"Scan '{scan_name}': Job-Existenz nicht prüfbar ({e}) - "
                "Ergebnis wird gespeichert"
            )
            job_exists = True

        if not job_exists:
            logger.info(
                f"Scan '{scan_name}': Job wurde während des Laufs gelöscht - "
                "Ergebnis wird verworfen"
            )
            return False

        storage.add_result(scan_slug, scan_name, scan_result, nas_host)
        return True

    def _set_expected_paths(self, scan_slug: str, paths: List[str]) -> None:
        """Hinterlegt die erwarteten Pfade (normalisiert) für die finished-Prüfung"""
        with self._state_lock:
            status = self._scan_status.get(scan_slug)
            if status is not None:
                status["expected_paths"] = [self._normalize_path(path) for path in paths]

    def _set_current_path(self, scan_slug: str, path: Optional[str]) -> None:
        """Setzt den aktuell gescannten Pfad"""
        with self._state_lock:
            status = self._scan_status.get(scan_slug)
            if status is not None:
                status["current_path"] = path

    def _set_path_status(self, scan_slug: str, path: str, values: Dict[str, Any]) -> None:
        """Setzt den Status eines einzelnen Pfads und aggregiert neu"""
        with self._state_lock:
            status = self._scan_status.get(scan_slug)
            if status is None:
                return
            status.setdefault("path_status", {})[self._normalize_path(path)] = values
            self._aggregate_path_status(scan_slug)

    def _mark_all_paths_finished(self, scan_slug: str) -> None:
        """Setzt den Scan-Status auf 'alle Pfade abgearbeitet'"""
        with self._state_lock:
            status = self._scan_status.get(scan_slug)
            if status is None:
                return
            status["finished"] = True
            status["current_path"] = None
            # Re-aggregieren, um sicherzustellen, dass alles korrekt ist
            self._aggregate_path_status(scan_slug)

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
        with self._state_lock:
            current_status = self._scan_status.get(scan_slug)
            if current_status is None:
                return

            # Initialisiere path_status falls nicht vorhanden
            if "path_status" not in current_status:
                current_status["path_status"] = {}

            self._aggregate_into(current_status)

    @staticmethod
    def _aggregate_into(current_status: dict) -> None:
        """Berechnet die aggregierten Werte eines Scan-Status neu"""
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
        
        # Markiere Scan als laufend - Prüfung und Markierung atomar, damit
        # zwei gleichzeitige Trigger nicht beide starten
        if not self._try_start_scan(scan_slug):
            logger.warning(f"Scan '{scan_name}' läuft bereits")
            # Erstelle ein temporäres "running" Result (wird nicht gespeichert)
            return ScanResult(
                scan_slug=scan_slug,
                scan_name=scan_name,
                timestamp=datetime.now(timezone.utc),
                status="running",
                results=[]
            )

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
                self._persist_result(scan_slug, scan_name, scan_result, scan_config.nas.host)
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
                    self._persist_result(scan_slug, scan_name, scan_result, scan_config.nas.host)
                    return scan_result
                
                logger.info(f"Scan '{scan_name}': {len(paths)} Pfad(e) zum Scannen gefunden: {paths}")
                
                # Speichere erwartete Pfade im Status für korrekte finished-Prüfung (normalisiert)
                self._set_expected_paths(scan_slug, paths)

                # Führe Scans für alle Pfade aus
                result_items = []
                
                # Erstelle Callback für Status-Updates für einen spezifischen Pfad
                def create_path_status_callback(path_to_scan: str):
                    """Erstellt einen Callback für Status-Updates für einen spezifischen Pfad"""
                    def update_scan_status(status_info: dict):
                        """Aktualisiert den intermediären Status des Scans für einen spezifischen Pfad"""
                        # Speichere Status für diesen spezifischen Pfad (normalisiert)
                        # und aggregiere die Werte aller Pfade
                        self._set_path_status(scan_slug, path_to_scan, {
                            "num_dir": status_info.get("num_dir", 0),
                            "num_file": status_info.get("num_file", 0),
                            "total_size": status_info.get("total_size", 0),
                            "waited": status_info.get("waited", 0),
                            "finished": status_info.get("finished", False),
                        })
                        # Aktualisiere current_path
                        self._set_current_path(scan_slug, path_to_scan)

                    return update_scan_status
                
                for idx, path in enumerate(paths, 1):
                    # Abbruch zwischen zwei Pfaden: kein weiterer Pfad wird
                    # begonnen, die bereits gemessenen bleiben erhalten.
                    if self.is_cancel_requested(scan_slug):
                        logger.info(
                            f"Scan '{scan_name}': Abbruch angefordert - "
                            f"überspringe die restlichen {len(paths) - idx + 1} Pfad(e)"
                        )
                        break

                    try:
                        logger.info(f"Scan '{scan_name}': [{idx}/{len(paths)}] Starte Scan von '{path}'")
                        path_start_time = datetime.now(timezone.utc)

                        # Setze current_path direkt beim Start des Pfads (bevor get_dir_size_async aufgerufen wird)
                        self._set_current_path(scan_slug, path)

                        # Erstelle Callback für diesen spezifischen Pfad
                        path_status_callback = create_path_status_callback(path)

                        # Übergib Callback an get_dir_size_async
                        result = await api.get_dir_size_async(
                            path,
                            max_wait=PATH_MAX_WAIT_SECONDS,
                            status_callback=path_status_callback,  # Callback für Status-Updates
                            # Erlaubt den Abbruch mitten in einem langen Pfad -
                            # ohne das würde ein hängender Pfad bis max_wait
                            # weiterlaufen.
                            cancel_check=lambda: self.is_cancel_requested(scan_slug),
                        )
                        path_duration = (datetime.now(timezone.utc) - path_start_time).total_seconds()
                        
                        if result is None:
                            # None kommt auch beim Abbruch - dann ist der Pfad
                            # nicht fehlgeschlagen, sondern wurde beendet.
                            cancelled = self.is_cancel_requested(scan_slug)
                            if cancelled:
                                logger.info(f"Scan '{scan_name}': [{idx}/{len(paths)}] Scan von '{path}' abgebrochen")
                            else:
                                logger.warning(f"Scan '{scan_name}': [{idx}/{len(paths)}] Scan von '{path}' fehlgeschlagen - keine Ergebnisse erhalten")
                            # Markiere Pfad als fertig (fehlgeschlagen) im Status (normalisiert)
                            self._set_path_status(scan_slug, path, {
                                "num_dir": 0,
                                "num_file": 0,
                                "total_size": 0,
                                "waited": 0,
                                "finished": True,
                            })

                            result_items.append(ScanResultItem(
                                folder_name=path,
                                success=False,
                                error=(
                                    "Abgebrochen" if cancelled
                                    else "Scan fehlgeschlagen - keine Ergebnisse erhalten"
                                )
                            ))
                            continue
                        
                        # Aktualisiere finalen Status für diesen Pfad mit den Ergebnissen (normalisiert)
                        self._set_path_status(scan_slug, path, {
                            "num_dir": result.get('num_dir', 0),
                            "num_file": result.get('num_file', 0),
                            "total_size": result.get('total_size', 0),
                            "waited": 0,
                            "finished": True,
                        })

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
                        # Markiere Pfad als fertig (fehlgeschlagen) im Status (normalisiert),
                        # damit _aggregate_path_status den Scan trotz Fehler als abgeschlossen erkennt
                        self._set_path_status(scan_slug, path, {
                            "num_dir": 0,
                            "num_file": 0,
                            "total_size": 0,
                            "waited": 0,
                            "finished": True,
                        })
                        result_items.append(ScanResultItem(
                            folder_name=path,
                            success=False,
                            error=f"Fehler beim Scannen: {str(e)}"
                        ))
                
                # Aktualisiere ScanResult mit allen Ergebnissen
                scan_result.results = result_items
                scan_result.timestamp = datetime.now(timezone.utc)  # Aktualisiere Timestamp
                
                # Alle Pfade sind jetzt gescannt: finished setzen, current_path leeren
                self._mark_all_paths_finished(scan_slug)

                total_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                successful = sum(1 for r in result_items if r.success)
                
                # Abbruch hat Vorrang vor der Erfolgs-/Fehlerbewertung: ein
                # bewusst beendeter Lauf ist kein Fehler, auch wenn dadurch
                # kein einziger Pfad fertig geworden ist.
                if self.is_cancel_requested(scan_slug):
                    scan_result.status = "cancelled"
                    scan_result.error = (
                        f"Abgebrochen nach {total_duration:.0f}s - "
                        f"{successful} von {len(paths)} Pfad(en) gemessen"
                    )
                    logger.info(
                        f"Scan '{scan_name}': === Abgebrochen === "
                        f"{successful}/{len(paths)} Pfad(e) gemessen, "
                        f"Gesamtdauer: {total_duration:.1f}s"
                    )
                # Prüfe ob mindestens ein erfolgreiches Ergebnis vorhanden ist
                elif successful == 0:
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
            # tz-bewusst, damit Zeitdifferenzen (z.B. Alters-Metriken) nicht scheitern
            scan_result.timestamp = datetime.now(timezone.utc)
        
        finally:
            # Markiere Scan als beendet, aber behalte Status für Grace Period
            self._finish_scan(scan_slug)

        # Speichere nur abgeschlossene Scans (completed oder failed)
        # "running" Status wird nicht gespeichert
        if scan_result.status != "running":
            self._persist_result(scan_slug, scan_name, scan_result, scan_config.nas.host)
        
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
