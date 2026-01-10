"""
DirSize Polling Helper Module
Enthält alle Hilfsfunktionen für das Polling von DirSize-Tasks.
"""
import time
import threading
import logging
from typing import Dict, Optional, List, Tuple, Callable

# Importiere console und logger aus explore_syno_api
# Da diese Module-Level-Variablen sind, müssen wir sie importieren
import sys
from pathlib import Path

# Füge das Projekt-Root zum Python-Pfad hinzu
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Importiere console und logger aus explore_syno_api
from explore_syno_api import console, logger


class DirSizePollingHelper:
    """
    Helper-Klasse für DirSize-Task-Polling.
    Kapselt alle Polling-Logik in einem separaten Modul.
    """
    
    def __init__(self, api_instance):
        """
        Initialisiert den Helper mit einer API-Instanz.
        
        Args:
            api_instance: Instanz von SynologyAPI
        """
        self.api = api_instance
    
    def check_shutdown_and_cleanup(self, shutdown_event: Optional[threading.Event], 
                                    task_id: str) -> bool:
        """
        Prüft ob Shutdown-Event gesetzt ist und räumt auf.
        
        Args:
            shutdown_event: Optionales Threading-Event für Shutdown-Signal
            task_id: Die Task-ID die aus _active_tasks entfernt werden soll
            
        Returns:
            True wenn Shutdown gesetzt ist (Abbruch), False sonst
        """
        if shutdown_event and shutdown_event.is_set():
            if task_id in self.api._active_tasks:
                self.api._active_tasks.remove(task_id)
            return True
        return False
    
    def start_dir_size_task(self, folder_path: str) -> Optional[str]:
        """
        Startet einen DirSize-Task auf dem Synology NAS.
        
        Args:
            folder_path: Pfad zum Verzeichnis das analysiert werden soll
            
        Returns:
            task_id wenn erfolgreich, None bei Fehler
        """
        response = self.api._api_call(
            "SYNO.FileStation.DirSize",
            "start",
            version="2",
            additional_params={"path": folder_path}
        )
        
        if not response:
            if not self.api.output_json:
                console.print(f"  [red]✗[/red] Keine Antwort vom Server erhalten")
            return None
        
        if response and response.get("success"):
            # Auswertung der Task-Start-Antwort
            data = response.get("data", {})
            task_id = data.get("taskid")
            
            if not task_id:
                if not self.api.output_json:
                    console.print(f"[red]✗[/red] Fehler: Task-Start erfolgreich, aber keine taskid in Antwort erhalten")
                    console.print(f"  Antwort-Daten: {data}")
                return None
            
            # Validiere Task-ID Format (sollte nicht leer sein)
            if not task_id or len(task_id.strip()) == 0:
                if not self.api.output_json:
                    console.print(f"[red]✗[/red] Fehler: Task-ID ist leer")
                return None
            
            return task_id
        
        return None
    
    def handle_initial_status_check(self, initial_status: Dict, task_id: str,
                                    start_time: float, waited: int,
                                    error_599_count: List[int]) -> Optional[Dict]:
        """
        Behandelt den initialen Status-Check nach Task-Start.
        
        Args:
            initial_status: Die Response vom initialen Status-Check
            task_id: Die Task-ID
            start_time: Startzeit des Tasks
            waited: Verstrichene Zeit in Sekunden
            error_599_count: Liste mit einem Element für mutable Referenz (wird bei 599-Fehler aktualisiert)
            
        Returns:
            Ergebnis-Dict wenn Task fertig, None sonst
        """
        # Prüfe ob Task bereits beim initialen Check fertig ist
        initial_result = self.api._check_and_handle_finished_task(
            initial_status, task_id, start_time, waited
        )
        if initial_result is not None:
            return initial_result
        elif initial_status and not initial_status.get("success"):
            # Nur bei fehlgeschlagenen Responses (success: false) Fehlerbehandlung
            error = initial_status.get("error", {})
            error_code = error.get("code", "unknown")
            # Meldung nur für andere Fehlercodes ausgeben, nicht für 599 (erwartet nach Abbruch)
            if not self.api.output_json and error_code != 599:
                console.print(f"  [yellow]⚠[/yellow] Erster Status-Check fehlgeschlagen (Code {error_code})")
            
            if error_code == 160:  # Task nicht gefunden
                if not self.api.output_json:
                    console.print(f"  [yellow]⏳[/yellow] Task nicht gefunden - warte 2 Sekunden und versuche erneut...")
                try:
                    time.sleep(2)
                except KeyboardInterrupt:
                    raise  # Sofort weiterleiten
                # Retry: Versuche nochmal einen Status-Check
                retry_status = self.api._api_call(
                    "SYNO.FileStation.DirSize",
                    "status",
                    version="2",
                    additional_params={"taskid": f'"{task_id}"'},  # taskid muss in Anführungszeichen sein
                    retry_on_error=False
                )
                if retry_status and retry_status.get("success"):
                    if not self.api.output_json:
                        console.print(f"  [green]✓[/green] Task nach Retry gefunden!")
                    retry_result = self.api._check_and_handle_finished_task(
                        retry_status, task_id, start_time, waited
                    )
                    if retry_result is not None:
                        return retry_result
                else:
                    if not self.api.output_json:
                        console.print(f"  [red]✗[/red] Task wurde auch nach Retry nicht gefunden - möglicherweise wurde er nicht korrekt angelegt")
                    if task_id in self.api._active_tasks:
                        self.api._active_tasks.remove(task_id)
                    return None
            elif error_code == 599:  # Fehler 599 beim initialen Check
                # Keine Meldung nötig - erwartet nach Abbruch, Task könnte noch starten
                error_599_count[0] = 1  # Setze Counter, damit er im Loop berücksichtigt wird
                # Fahre mit dem Loop fort, nicht abbrechen
            else:
                # Anderer Fehler - fahre mit dem Loop fort
                if not self.api.output_json:
                    console.print(f"  [yellow]⚠[/yellow] Anderer Fehler ({error_code}) - fahre mit Polling fort")
        elif initial_status is None:
            # Keine Antwort vom Server erhalten
            if not self.api.output_json:
                console.print(f"  [yellow]⚠[/yellow] Erster Status-Check: Keine Antwort erhalten (Timeout?)")
            # Nicht abbrechen, könnte temporäres Problem sein
        # else: initial_status ist erfolgreich, aber Task noch nicht fertig - fahre einfach mit Polling fort
        
        return None
    
    def check_timeout_and_final_status(self, task_id: str, waited: int,
                                       max_wait: int, start_time: float) -> Optional[Dict]:
        """
        Prüft ob Timeout erreicht wurde und macht finalen Status-Check.
        
        Args:
            task_id: Die Task-ID
            waited: Verstrichene Zeit in Sekunden
            max_wait: Maximale Wartezeit in Sekunden
            start_time: Startzeit des Tasks
            
        Returns:
            Ergebnis-Dict wenn Task doch noch fertig, None bei Timeout
        """
        if waited >= max_wait:
            if not self.api.output_json:
                console.print(f"  [yellow]⏳[/yellow] Timeout-Limit erreicht ({waited}s) - mache letzten Status-Check...")
            # Letzter Versuch: Prüfe ob Task vielleicht doch fertig ist
            final_status_check = self.api._api_call(
                "SYNO.FileStation.DirSize",
                "status",
                version="2",
                additional_params={"taskid": f'"{task_id}"'},
                retry_on_error=False
            )
            # Prüfe ob Task beim Timeout-Check doch noch fertig ist
            timeout_result = self.api._check_and_handle_finished_task(
                final_status_check, task_id, start_time, waited
            )
            if timeout_result is not None:
                if not self.api.output_json:
                    console.print(f"  [green]✓[/green] Task doch noch abgeschlossen nach {waited}s")
                return timeout_result
        return None
    
    def update_polling_interval(self, data: Dict, current_interval: int,
                                min_interval: int, max_interval: int,
                                last_progress: Optional[float],
                                no_progress_count: int,
                                last_num_dir: Optional[int] = None,
                                last_num_file: Optional[int] = None,
                                last_total_size: Optional[int] = None) -> Tuple[int, Optional[float], int]:
        """
        Aktualisiert das Polling-Intervall basierend auf Fortschritt.
        
        Args:
            data: Die 'data' Sektion aus der Status-Response
            current_interval: Aktuelles Polling-Intervall in Sekunden
            min_interval: Minimales Polling-Intervall in Sekunden
            max_interval: Maximales Polling-Intervall in Sekunden
            last_progress: Letzter Fortschrittswert (None wenn noch kein Fortschritt)
            no_progress_count: Anzahl Polls ohne Fortschritt
            last_num_dir: Letzte Anzahl Verzeichnisse (für Fortschrittserkennung)
            last_num_file: Letzte Anzahl Dateien (für Fortschrittserkennung)
            last_total_size: Letzte Gesamtgröße (für Fortschrittserkennung)
            
        Returns:
            Tuple mit (neues_intervall, neuer_last_progress, neuer_no_progress_count)
        """
        current_progress = data.get("progress", 0)
        processed_num = data.get("processed_num", -1)
        
        # Extrahiere intermediäre Status-Informationen für Fortschrittserkennung
        current_num_dir = data.get("num_dir", 0)
        current_num_file = data.get("num_file", 0)
        current_total_size = data.get("total_size", 0)
        
        # Prüfe ob Fortschritt erkannt wurde
        progress_detected = False
        
        # 1. Prüfe progress/processed_num (wenn verfügbar)
        if current_progress is not None and last_progress is not None:
            if current_progress > last_progress:
                progress_detected = True
        elif last_progress is not None:
            # current_progress ist None, aber last_progress nicht - prüfe processed_num
            if processed_num >= 0 and processed_num > (last_progress or 0):
                progress_detected = True
        
        # 2. Prüfe num_dir, num_file, total_size (wenn progress/processed_num nicht verfügbar oder unverändert)
        if not progress_detected:
            # Prüfe ob sich num_dir, num_file oder total_size geändert haben
            if last_num_dir is not None and current_num_dir > last_num_dir:
                progress_detected = True
            elif last_num_file is not None and current_num_file > last_num_file:
                progress_detected = True
            elif last_total_size is not None and current_total_size > last_total_size:
                progress_detected = True
        
        # 3. Reagiere auf Fortschritt
        if progress_detected:
            # Fortschritt erkannt: Setze Intervall zurück
            if current_interval > min_interval:
                logger.debug(f"Fortschritt erkannt, setze Polling-Intervall zurück auf {min_interval}s")
                current_interval = min_interval
            no_progress_count = 0
        else:
            # Kein Fortschritt: Erhöhe Intervall schrittweise
            no_progress_count += 1
            if no_progress_count >= 3 and current_interval < max_interval:
                # Erhöhe Intervall um 2 Sekunden, aber nicht über Maximum
                new_interval = min(current_interval + 2, max_interval)
                if new_interval != current_interval:
                    logger.debug(f"Kein Fortschritt seit {no_progress_count} Polls, erhöhe Intervall auf {new_interval}s")
                    current_interval = new_interval
        
        # Aktualisiere letzten Fortschritt
        new_last_progress = current_progress if current_progress is not None else processed_num
        
        return (current_interval, new_last_progress, no_progress_count)
    
    def process_status_response(self, status_response: Dict, task_id: str,
                                waited: int, current_poll_interval: int,
                                min_poll_interval: int, max_poll_interval: int,
                                last_progress: Optional[float],
                                no_progress_count: int,
                                last_status_print: int,
                                status_callback: Optional[Callable] = None,
                                progress_update_callback: Optional[Callable] = None,
                                folder_name: Optional[str] = None,
                                last_num_dir: Optional[int] = None,
                                last_num_file: Optional[int] = None,
                                last_total_size: Optional[int] = None) -> Tuple[int, Optional[float], int, int, Optional[int], Optional[int], Optional[int]]:
        """
        Verarbeitet eine Status-Response und aktualisiert Polling-Parameter.
        
        Args:
            status_response: Die vollständige Status-Response
            task_id: Die Task-ID
            waited: Verstrichene Zeit in Sekunden
            current_poll_interval: Aktuelles Polling-Intervall
            min_poll_interval: Minimales Polling-Intervall
            max_poll_interval: Maximales Polling-Intervall
            last_progress: Letzter Fortschrittswert
            no_progress_count: Anzahl Polls ohne Fortschritt
            last_status_print: Letzter Zeitpunkt für Status-Print
            status_callback: Optionaler Callback für Status-Updates (für FastAPI-Server)
                            Wird mit Dict aufgerufen: {num_dir, num_file, total_size, waited, finished}
            progress_update_callback: Optionaler Callback für Rich Progress Updates
            folder_name: Ordnername für Progress-Description
            last_num_dir: Letzte Anzahl Verzeichnisse (für Fortschrittserkennung)
            last_num_file: Letzte Anzahl Dateien (für Fortschrittserkennung)
            last_total_size: Letzte Gesamtgröße (für Fortschrittserkennung)
            
        Returns:
            Tuple mit (neues_intervall, neuer_last_progress, neuer_no_progress_count, neuer_last_status_print, 
                      neuer_last_num_dir, neuer_last_num_file, neuer_last_total_size)
        """
        if not status_response or not status_response.get("success"):
            return (current_poll_interval, last_progress, no_progress_count, last_status_print, 
                    last_num_dir, last_num_file, last_total_size)
        
        data = status_response["data"]
        
        # Extrahiere intermediäre Status-Informationen
        num_dir = data.get("num_dir", 0)
        num_file = data.get("num_file", 0)
        total_size = data.get("total_size", 0)
        finished = data.get("finished", False)
        
        # Rufe Callback auf, wenn vorhanden (für FastAPI-Server)
        if status_callback:
            try:
                status_callback({
                    "num_dir": num_dir,
                    "num_file": num_file,
                    "total_size": total_size,
                    "waited": waited,
                    "finished": finished
                })
            except Exception as e:
                logger.warning(f"Fehler beim Aufruf des Status-Callbacks: {e}")
        
        # Adaptive Polling: Prüfe Fortschritt und passe Intervall an
        # Verwende num_dir, num_file, total_size für Fortschrittserkennung
        current_poll_interval, last_progress, no_progress_count = self.update_polling_interval(
            data, current_poll_interval, min_poll_interval, max_poll_interval,
            last_progress, no_progress_count,
            last_num_dir=last_num_dir,
            last_num_file=last_num_file,
            last_total_size=last_total_size
        )
        
        # CLI: Zeige intermediäre Informationen bei JEDEM Poll (nicht nur alle 10 Sekunden)
        # WICHTIG: Wenn progress_update_callback vorhanden ist, verwende diesen statt console.print()
        if not self.api.output_json:
            # Formatiere Größe für Ausgabe
            size_formatted = None
            if total_size > 0:
                try:
                    size_formatted = self.api._format_size_with_unit(total_size)
                except Exception:
                    pass
            
            # Erstelle Status-Info mit intermediären Informationen
            status_parts = []
            if num_dir > 0:
                status_parts.append(f"{num_dir:,} Ordner")
            if num_file > 0:
                status_parts.append(f"{num_file:,} Dateien")
            if size_formatted:
                status_parts.append(f"{size_formatted['size_formatted']:.2f} {size_formatted['unit']}")
            
            # Wenn Progress-Update-Callback vorhanden, verwende diesen (für Rich Progress)
            if progress_update_callback and status_parts and folder_name:
                try:
                    description = f"[green]Checking {folder_name} - {' | '.join(status_parts)}[/green]"
                    progress_update_callback(description)
                except Exception as e:
                    logger.warning(f"Fehler beim Progress-Update-Callback: {e}")
            # Sonst normale Console-Ausgabe (nur wenn kein Rich Progress aktiv)
            elif not progress_update_callback and status_parts:
                status_info = f"  ⏳ Berechnung läuft... ({waited}s) - {' | '.join(status_parts)}"
                console.print(status_info)
        
        # Detaillierte Task-Status-Logs (alle 10 Sekunden für zusätzliche Details)
        if waited - last_status_print >= 10:
            progress = data.get("progress", 0)
            processed_num = data.get("processed_num", -1)
            processed_size = data.get("processed_size", -1)
            total = data.get("total", -1)
            processing_path = data.get("processing_path", "")
            
            if progress > 0 or processed_num >= 0 or processing_path:
                detail_info = f"  📊 Details ({waited}s)"
                if progress > 0:
                    detail_info += f" - Fortschritt: {progress*100:.1f}%"
                if processed_num >= 0 and total >= 0:
                    detail_info += f" - Verarbeitet: {processed_num}/{total}"
                if processing_path:
                    detail_info += f" - Aktuell: {processing_path}"
                if not self.api.output_json:
                    console.print(detail_info)
            last_status_print = waited
        
        # Task noch nicht fertig - Debug-Log
        if logger.isEnabledFor(logging.DEBUG):
            finished_value = data.get("finished")
            logger.debug(f"Task noch nicht fertig (finished={finished_value})")
            logger.debug(f"  Intermediär: {num_dir} Ordner, {num_file} Dateien, {total_size} Bytes")
        
        # Aktualisiere letzte Werte für nächsten Poll
        new_last_num_dir = num_dir if num_dir > 0 else last_num_dir
        new_last_num_file = num_file if num_file > 0 else last_num_file
        new_last_total_size = total_size if total_size > 0 else last_total_size
        
        return (current_poll_interval, last_progress, no_progress_count, last_status_print,
                new_last_num_dir, new_last_num_file, new_last_total_size)
    
    def handle_error_599(self, task_id: str, error_599_count: int,
                         max_error_599: int, waited: int,
                         last_status_print: int, start_time: float) -> Tuple[int, Optional[Dict], int]:
        """
        Behandelt Fehler 599 (Service unavailable).
        
        Args:
            task_id: Die Task-ID
            error_599_count: Aktueller 599-Fehler-Counter
            max_error_599: Maximal erlaubte 599-Fehler
            waited: Verstrichene Zeit in Sekunden
            last_status_print: Letzter Zeitpunkt für Status-Print
            start_time: Startzeit des Tasks
            
        Returns:
            Tuple mit (neuer_error_599_count, ergebnis_dict_oder_none, neuer_last_status_print)
            Wenn ergebnis_dict_oder_none ein Dict ist, sollte die Funktion beendet werden.
            Wenn es None ist, sollte weiter gemacht werden.
        """
        error_599_count += 1
        if waited - last_status_print >= 10:
            print(f"  ⚠ Status-Check Fehler 599 (Versuch {error_599_count}/{max_error_599}) - könnte Task-Problem sein ({waited}s)")
            last_status_print = waited
        
        # Frühere Prüfung: Nach 2 Fehlern prüfen, ob Task in BackgroundTask API existiert
        if error_599_count == 2:
            print(f"  🔍 Prüfe nach 2 Fehlern, ob Task in BackgroundTask API existiert...")
            bg_check_response = self.api._api_call(
                "SYNO.FileStation.BackgroundTask",
                "list",
                version="3",
                additional_params={"api_filter": "SYNO.FileStation.DirSize"},
                retry_on_error=False
            )
            if bg_check_response and bg_check_response.get("success"):
                tasks = bg_check_response["data"].get("tasks", [])
                task_found = any(t.get("taskid") == task_id for t in tasks)
                if task_found:
                    print(f"  ✓ Task existiert in BackgroundTask API - setze Counter zurück und warte länger")
                    error_599_count = 0  # Reset, da Task existiert
                    # Warte länger vor nächstem Check (5 Sekunden statt 2)
                    try:
                        time.sleep(3)  # Zusätzliche 3 Sekunden Wartezeit
                    except KeyboardInterrupt:
                        raise  # Sofort weiterleiten
                else:
                    print(f"  ⚠ Task nicht in BackgroundTask API gefunden")
        
        # Wenn zu viele 599-Fehler, prüfe ob Task noch existiert
        if error_599_count >= max_error_599:
            print(f"⚠ {max_error_599} mal Fehler 599 - prüfe ob Task noch existiert...")
            bg_response = self.api._api_call(
                "SYNO.FileStation.BackgroundTask",
                "list",
                version="3",
                additional_params={"api_filter": "SYNO.FileStation.DirSize"},
                retry_on_error=False
            )
            
            if bg_response and bg_response.get("success"):
                tasks = bg_response["data"].get("tasks", [])
                task_found = None
                for t in tasks:
                    if t.get("taskid") == task_id:
                        task_found = t
                        break
                
                if not task_found:
                    print(f"⚠ Task {task_id} existiert nicht mehr auf dem NAS (Fehler 599)")
                    print(f"  🔍 Prüfe ob Task vielleicht bereits beendet wurde...")
                    
                    # Versuche einen letzten Status-Check über DirSize API
                    final_status = self.api._api_call(
                        "SYNO.FileStation.DirSize",
                        "status",
                        version="2",
                        additional_params={"taskid": f'"{task_id}"'},  # taskid muss in Anführungszeichen sein
                        retry_on_error=False
                    )
                    
                    if final_status and final_status.get("success"):
                        final_data = final_status.get("data", {})
                        if final_data.get("finished"):
                            # Task ist doch noch da und fertig!
                            print(f"  ✓ Task doch noch gefunden und bereits abgeschlossen!")
                            self.api._active_tasks.remove(task_id)
                            result = (
                                final_data.get("num_dir", 0),
                                final_data.get("num_file", 0),
                                final_data.get("total_size", 0)
                            )
                            # Berechne Laufzeit
                            elapsed_time = time.time() - start_time
                            result_dict = {
                                "num_dir": result[0],
                                "num_file": result[1],
                                "total_size": result[2],
                                "elapsed_time": round(elapsed_time, 2)
                            }
                            return (error_599_count, result_dict, last_status_print)
                    
                    print(f"  ✗ Task wurde nicht gefunden und ist nicht mehr verfügbar")
                    if task_id in self.api._active_tasks:
                        self.api._active_tasks.remove(task_id)
                    return (error_599_count, None, last_status_print)  # None = sollte abgebrochen werden
                else:
                    # Task existiert noch in BackgroundTask API
                    if task_found.get("finished"):
                        # Task ist beendet - versuche Ergebnisse zu bekommen
                        print(f"  ✓ Task existiert noch und ist beendet - hole Ergebnisse...")
                        # Versuche Status über DirSize API zu bekommen
                        final_status = self.api._api_call(
                            "SYNO.FileStation.DirSize",
                            "status",
                            version="2",
                            additional_params={"taskid": f'"{task_id}"'},  # taskid muss in Anführungszeichen sein
                            retry_on_error=False
                        )
                        if final_status and final_status.get("success"):
                            final_data = final_status.get("data", {})
                            if final_data.get("finished"):
                                self.api._active_tasks.remove(task_id)
                                result = (
                                    final_data.get("num_dir", 0),
                                    final_data.get("num_file", 0),
                                    final_data.get("total_size", 0)
                                )
                                # Berechne Laufzeit
                                elapsed_time = time.time() - start_time
                                result_dict = {
                                    "num_dir": result[0],
                                    "num_file": result[1],
                                    "total_size": result[2],
                                    "elapsed_time": round(elapsed_time, 2)
                                }
                                return (error_599_count, result_dict, last_status_print)
                    else:
                        # Task existiert noch und läuft - reset Counter und versuche weiter
                        print(f"  ✓ Task {task_id} existiert noch und läuft - setze Counter zurück und versuche weiter")
                        error_599_count = 0
            else:
                # Konnte BackgroundTask API nicht abfragen - abbrechen
                print(f"✗ Konnte Task-Status nicht überprüfen (Fehler 599) - beende Warte-Loop")
                if task_id in self.api._active_tasks:
                    self.api._active_tasks.remove(task_id)
                return (error_599_count, None, last_status_print)  # None = sollte abgebrochen werden
        
        return (error_599_count, None, last_status_print)  # None = sollte nicht abgebrochen werden (weiter machen)
    
    def poll_task_status(self, task_id: str, start_time: float, max_wait: int,
                         poll_interval: int, shutdown_event: Optional[threading.Event],
                         error_599_count: int,
                         status_callback: Optional[Callable] = None,
                         progress_update_callback: Optional[Callable] = None,
                         folder_name: Optional[str] = None) -> Optional[Dict]:
        """
        Führt die Polling-Schleife für einen Task durch.
        
        Args:
            task_id: Die Task-ID
            start_time: Startzeit des Tasks
            max_wait: Maximale Wartezeit in Sekunden
            poll_interval: Basis-Polling-Intervall in Sekunden
            shutdown_event: Optionales Threading-Event für Shutdown-Signal
            error_599_count: Initialer 599-Fehler-Counter
            status_callback: Optionaler Callback für Status-Updates (für FastAPI-Server)
            
        Returns:
            Ergebnis-Dict wenn fertig, None bei Timeout/Fehler
        """
        # Initialisiere Polling-Variablen
        waited = 0
        last_status_print = 0
        failed_status_checks = 0
        max_failed_checks = 5
        max_error_599 = 3
        
        # Adaptive Polling: Start mit kurzem Intervall, erhöhe bei keinem Fortschritt
        min_poll_interval = poll_interval
        max_poll_interval = 10
        current_poll_interval = min_poll_interval
        last_progress = None
        no_progress_count = 0
        
        # Track letzte Werte für Fortschrittserkennung basierend auf num_dir, num_file, total_size
        last_num_dir = None
        last_num_file = None
        last_total_size = None
        
        try:
            while waited < max_wait:
                # Prüfe, ob Shutdown-Event gesetzt ist (Thread-Abbruch)
                if self.check_shutdown_and_cleanup(shutdown_event, task_id):
                    return None
                
                # Längere Wartezeit bei 599-Fehlern
                if error_599_count > 0:
                    # Bei 599-Fehlern warte 5 Sekunden statt 2
                    wait_time = 5
                    if not self.api.output_json:
                        console.print(f"  [yellow]⏳[/yellow] Warte {wait_time}s (längere Pause wegen 599-Fehler)...")
                    try:
                        time.sleep(wait_time)
                    except KeyboardInterrupt:
                        # Sofort weiterleiten - beendet die Schleife und Funktion
                        raise
                    # Prüfe erneut nach Sleep
                    if self.check_shutdown_and_cleanup(shutdown_event, task_id):
                        return None
                    waited += wait_time
                else:
                    # Adaptive Polling: Verwende aktuelles Intervall
                    try:
                        time.sleep(current_poll_interval)
                    except KeyboardInterrupt:
                        # Sofort weiterleiten - beendet die Schleife und Funktion
                        raise
                    # Prüfe erneut nach Sleep
                    if self.check_shutdown_and_cleanup(shutdown_event, task_id):
                        return None
                    waited += current_poll_interval
                
                # Prüfe nach dem Sleep, ob Timeout erreicht wurde
                timeout_result = self.check_timeout_and_final_status(
                    task_id, waited, max_wait, start_time
                )
                if timeout_result is not None:
                    return timeout_result
                if waited >= max_wait:
                    # Timeout wirklich erreicht
                    break  # Verlasse die while-Schleife
                
                # Prüfe erneut, ob Shutdown-Event gesetzt ist (vor API-Call)
                if self.check_shutdown_and_cleanup(shutdown_event, task_id):
                    return None
                
                # Status-Check nach jedem Sleep
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Status-Check nach {waited}s (Poll-Intervall: {current_poll_interval}s)")
                
                status_response = self.api._api_call(
                    "SYNO.FileStation.DirSize",
                    "status",
                    version="2",
                    additional_params={"taskid": f'"{task_id}"'},  # taskid muss in Anführungszeichen sein
                    retry_on_error=False
                )
                
                # Prüfe erneut nach API-Call
                if self.check_shutdown_and_cleanup(shutdown_event, task_id):
                    return None
                
                # WICHTIG: Prüfe finished SOFORT nach Status-Check, bevor andere Logik
                # Diese Prüfung MUSS ausgeführt werden, unabhängig von anderen Bedingungen
                finished_result = self.api._check_and_handle_finished_task(
                    status_response, task_id, start_time, waited
                )
                if finished_result is not None:
                    return finished_result
                
                # DEBUG: Zeige vollständige Response (nach finished-Prüfung)
                if logger.isEnabledFor(logging.DEBUG):
                    if status_response:
                        logger.debug(f"Status-Response erhalten - success={status_response.get('success')}")
                        if status_response.get("success"):
                            data = status_response.get("data", {})
                            finished_raw = data.get("finished")
                            finished_type = type(finished_raw).__name__
                            logger.debug(f"  finished={finished_raw} (Typ: {finished_type})")
                            logger.debug(f"  progress={data.get('progress')}, processed_num={data.get('processed_num')}, total={data.get('total')}")
                        else:
                            error = status_response.get("error", {})
                            logger.debug(f"  API-Fehler - Code: {error.get('code')}, Message: {error.get('message', 'N/A')}")
                    else:
                        logger.debug("  Keine Response erhalten (None)")
                
                if status_response and status_response.get("success"):
                    # Erfolgreicher Status-Check - Reset Counter
                    failed_status_checks = 0
                    error_599_count = 0  # Reset 599-Counter bei erfolgreichem Check
                    
                    # Verarbeite Status-Response und aktualisiere Polling-Parameter
                    current_poll_interval, last_progress, no_progress_count, last_status_print, \
                    last_num_dir, last_num_file, last_total_size = self.process_status_response(
                        status_response, task_id, waited, current_poll_interval,
                        min_poll_interval, max_poll_interval, last_progress,
                        no_progress_count, last_status_print,
                        status_callback=status_callback,  # Callback weiterreichen
                        progress_update_callback=progress_update_callback,  # Progress-Callback weiterreichen
                        folder_name=folder_name,  # Ordnername für Progress-Description
                        last_num_dir=last_num_dir,  # Letzte Werte für Fortschrittserkennung
                        last_num_file=last_num_file,
                        last_total_size=last_total_size
                    )
                elif status_response:
                    # API-Fehler beim Status-Check
                    failed_status_checks = 0  # Reset bei API-Antwort (auch wenn Fehler)
                    error = status_response.get("error", {})
                    error_code = error.get("code", "unknown")
                    
                    # Vollständige Fehlerantwort ausgeben
                    if waited - last_status_print >= 10:
                        print(f"  ⚠ Status-Check Fehler (Code {error_code}) - Vollständige Antwort: {status_response}")
                        last_status_print = waited
                    
                    if error_code == 160:  # Task nicht gefunden
                        print(f"⚠ Task {task_id} nicht mehr gefunden")
                        print(f"  🔍 Vollständige Fehlerantwort: {status_response}")
                        if task_id in self.api._active_tasks:
                            self.api._active_tasks.remove(task_id)
                        return None
                    elif error_code == 599:  # Spezieller Fehler - könnte Task-Problem sein
                        # Behandle 599-Fehler
                        new_error_599_count, result_dict, new_last_status_print = self.handle_error_599(
                            task_id, error_599_count, max_error_599, waited, last_status_print, start_time
                        )
                        error_599_count = new_error_599_count
                        last_status_print = new_last_status_print
                        
                        # Wenn Ergebnis-Dict zurückgegeben wurde, beende Funktion
                        if result_dict is not None:
                            return result_dict
                    else:
                        # Anderer API-Fehler - ausgeben aber weiter versuchen
                        error_599_count = 0  # Reset 599-Counter bei anderen Fehlern
                        if waited - last_status_print >= 10:
                            print(f"  ⚠ Status-Check Fehler (Code {error_code}), versuche weiter... ({waited}s)")
                            last_status_print = waited
                else:
                    # status_response ist None (Timeout oder Verbindungsfehler)
                    failed_status_checks += 1
                    if waited - last_status_print >= 10:
                        print(f"  ⚠ Status-Check fehlgeschlagen (keine Antwort/Timeout) - Versuch {failed_status_checks}/{max_failed_checks} ({waited}s)")
                        print(f"  🔍 Task-ID: {task_id}")
                        last_status_print = waited
                    
                    # Wenn zu viele Status-Checks fehlschlagen, prüfe ob Task noch existiert
                    if failed_status_checks >= max_failed_checks:
                        print(f"⚠ {max_failed_checks} Status-Checks hintereinander fehlgeschlagen - prüfe ob Task noch existiert...")
                        # Prüfe über BackgroundTask API ob Task noch läuft
                        bg_response = self.api._api_call(
                            "SYNO.FileStation.BackgroundTask",
                            "list",
                            version="3",
                            additional_params={"api_filter": "SYNO.FileStation.DirSize"},
                            retry_on_error=False
                        )
                        
                        if bg_response and bg_response.get("success"):
                            tasks = bg_response["data"].get("tasks", [])
                            task_found = any(t.get("taskid") == task_id for t in tasks)
                            if not task_found:
                                print(f"⚠ Task {task_id} existiert nicht mehr auf dem NAS - beende Warte-Loop")
                                if task_id in self.api._active_tasks:
                                    self.api._active_tasks.remove(task_id)
                                return None
                            else:
                                # Task existiert noch - reset Counter und versuche weiter
                                print(f"  ✓ Task {task_id} existiert noch - setze Counter zurück und versuche weiter")
                                failed_status_checks = 0
                        else:
                            # Konnte BackgroundTask API nicht abfragen - abbrechen
                            print(f"✗ Konnte Task-Status nicht überprüfen - beende Warte-Loop")
                            if task_id in self.api._active_tasks:
                                self.api._active_tasks.remove(task_id)
                            return None
        except KeyboardInterrupt:
            # KeyboardInterrupt während des Scans
            # Stelle sicher, dass task_id aus _active_tasks entfernt wird
            if task_id in self.api._active_tasks:
                self.api._active_tasks.remove(task_id)
            if not self.api.output_json:
                console.print(f"\n[yellow]⚠[/yellow] Abbruch durch Benutzer")
            raise  # Weiterleiten an übergeordnete Handler
        
        # Timeout erreicht
        if not self.api.output_json:
            console.print(f"[yellow]⚠[/yellow] Timeout nach {max_wait}s")
        return None
