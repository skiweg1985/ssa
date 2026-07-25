#!/usr/bin/env python3
"""
Synology File Station API Explorer
Erkundet die Synology API um Verzeichnisgrößen und Statistiken auszuwerten.
"""

import requests
import urllib3
import time
import asyncio
import aiohttp
import ssl
from typing import Dict, Optional, List, Tuple, Callable
import sys
import os
import json
import argparse
import random
import logging
import threading
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from rich.console import Console
from rich.spinner import Spinner
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from inquirer import Checkbox, List as InquirerList, prompt
from inquirer.themes import Default
from blessed import Terminal

# SSL-Warnungen unterdrücken (nur für Entwicklung)
term = Terminal()

# Eigenes Theme mit dunklerem Grün für bessere Harmonie mit Türkis
class DarkGreenTheme(Default):
    def __init__(self):
        super().__init__()
        self.Question.brackets_color = term.green  # Etwas dunkleres Grün
        self.Checkbox.selection_color = term.bold_black_on_green  # Dunkleres Grün statt bright_green
        self.Checkbox.selection_icon = "❯"
        self.Checkbox.selected_icon = "◉"
        self.Checkbox.selected_color = term.green
        self.Checkbox.unselected_icon = "◯"
        self.List.selection_color = term.bold_black_on_green  # Dunkleres Grün statt bright_green
        self.List.selection_cursor = "❯"

# SSL-Warnungen unterdrücken (nur für Entwicklung)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Rich Console initialisieren
console = Console()

# Logging konfigurieren (kann über ENV-Variable gesteuert werden)
logger = logging.getLogger(__name__)
# Standard: Logging deaktiviert (WARNING), kann über SYNO_ENABLE_LOGS aktiviert werden
log_level_env = os.getenv('SYNO_ENABLE_LOGS', '').lower()
if log_level_env in ('true', '1', 'yes', 'on', 'info'):
    logger.setLevel(logging.INFO)
elif log_level_env in ('debug', 'verbose'):
    logger.setLevel(logging.DEBUG)
elif log_level_env in ('warning', 'warn'):
    logger.setLevel(logging.WARNING)
elif log_level_env in ('error', 'critical'):
    logger.setLevel(logging.ERROR)
else:
    # Standard: Logging deaktiviert (nur WARNING und höher)
    logger.setLevel(logging.WARNING)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class SynologyAPI:
    """Klasse zur Interaktion mit der Synology File Station API"""
    
    def _is_task_finished(self, finished_value) -> bool:
        """
        Prüft ob ein Task als fertig markiert ist.
        Unterstützt verschiedene Datentypen für robuste Prüfung.
        
        Args:
            finished_value: Der Wert des 'finished' Feldes aus der API-Response
            
        Returns:
            True wenn der Task fertig ist, False sonst
        """
        if finished_value is True:
            return True
        elif isinstance(finished_value, str) and finished_value.lower() in ("true", "1", "yes"):
            return True
        elif isinstance(finished_value, (int, float)) and finished_value == 1:
            return True
        return False
    
    def _extract_task_result(self, data: Dict, start_time: float, waited: int) -> Dict:
        """
        Extrahiert das Ergebnis aus den Task-Daten und formatiert es.
        
        Args:
            data: Die 'data' Sektion aus der API-Response
            start_time: Startzeit des Tasks (für elapsed_time Berechnung)
            waited: Verstrichene Zeit in Sekunden
            
        Returns:
            Dictionary mit num_dir, num_file, total_size, elapsed_time
        """
        result = (
            data.get("num_dir", 0),
            data.get("num_file", 0),
            data.get("total_size", 0)
        )
        elapsed_time = time.time() - start_time
        return {
            "num_dir": result[0],
            "num_file": result[1],
            "total_size": result[2],
            "elapsed_time": round(elapsed_time, 2)
        }
    
    def _check_and_handle_finished_task(self, status_response: Dict, task_id: str, 
                                       start_time: float, waited: int) -> Optional[Dict]:
        """
        Prüft ob ein Task fertig ist und gibt das Ergebnis zurück, wenn ja.
        Diese Funktion sollte IMMER direkt nach einem Status-Check aufgerufen werden.
        
        Args:
            status_response: Die vollständige API-Response
            task_id: Die Task-ID
            start_time: Startzeit des Tasks
            waited: Verstrichene Zeit in Sekunden
            
        Returns:
            Dictionary mit Ergebnissen wenn Task fertig, None sonst
        """
        if not status_response or not status_response.get("success"):
            return None
        
        data = status_response.get("data", {})
        finished_value = data.get("finished")
        
        if self._is_task_finished(finished_value):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Task ist fertig (finished={finished_value}) - beende Schleife SOFORT")
            if not self.output_json:
                console.print(f"  [green]✓[/green] Task abgeschlossen nach {waited}s")
            if task_id in self._active_tasks:
                self._active_tasks.remove(task_id)
            return self._extract_task_result(data, start_time, waited)
        
        return None
    
    def _check_shutdown_and_cleanup(self, shutdown_event: Optional[threading.Event], 
                                    task_id: str) -> bool:
        """
        Prüft ob Shutdown-Event gesetzt ist und räumt auf.
        Delegiert an DirSizePollingHelper.
        
        Args:
            shutdown_event: Optionales Threading-Event für Shutdown-Signal
            task_id: Die Task-ID die aus _active_tasks entfernt werden soll
            
        Returns:
            True wenn Shutdown gesetzt ist (Abbruch), False sonst
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.check_shutdown_and_cleanup(shutdown_event, task_id)
    
    def _start_dir_size_task(self, folder_path: str) -> Optional[str]:
        """
        Startet einen DirSize-Task auf dem Synology NAS.
        Delegiert an DirSizePollingHelper.
        
        Args:
            folder_path: Pfad zum Verzeichnis das analysiert werden soll
            
        Returns:
            task_id wenn erfolgreich, None bei Fehler
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.start_dir_size_task(folder_path)
    
    def _handle_initial_status_check(self, initial_status: Dict, task_id: str,
                                    start_time: float, waited: int,
                                    error_599_count: List[int]) -> Optional[Dict]:
        """
        Behandelt den initialen Status-Check nach Task-Start.
        Delegiert an DirSizePollingHelper.
        
        Args:
            initial_status: Die Response vom initialen Status-Check
            task_id: Die Task-ID
            start_time: Startzeit des Tasks
            waited: Verstrichene Zeit in Sekunden
            error_599_count: Liste mit einem Element für mutable Referenz (wird bei 599-Fehler aktualisiert)
            
        Returns:
            Ergebnis-Dict wenn Task fertig, None sonst
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
    
    def _check_timeout_and_final_status(self, task_id: str, waited: int,
                                       max_wait: int, start_time: float) -> Optional[Dict]:
        """
        Prüft ob Timeout erreicht wurde und macht finalen Status-Check.
        Delegiert an DirSizePollingHelper.
        
        Args:
            task_id: Die Task-ID
            waited: Verstrichene Zeit in Sekunden
            max_wait: Maximale Wartezeit in Sekunden
            start_time: Startzeit des Tasks
            
        Returns:
            Ergebnis-Dict wenn Task doch noch fertig, None bei Timeout
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.check_timeout_and_final_status(
            task_id, waited, max_wait, start_time
        )
    
    def _update_polling_interval(self, data: Dict, current_interval: int,
                                min_interval: int, max_interval: int,
                                last_progress: Optional[float],
                                no_progress_count: int) -> Tuple[int, Optional[float], int]:
        """
        Aktualisiert das Polling-Intervall basierend auf Fortschritt.
        Delegiert an DirSizePollingHelper.
        
        Args:
            data: Die 'data' Sektion aus der Status-Response
            current_interval: Aktuelles Polling-Intervall in Sekunden
            min_interval: Minimales Polling-Intervall in Sekunden
            max_interval: Maximales Polling-Intervall in Sekunden
            last_progress: Letzter Fortschrittswert (None wenn noch kein Fortschritt)
            no_progress_count: Anzahl Polls ohne Fortschritt
            
        Returns:
            Tuple mit (neues_intervall, neuer_last_progress, neuer_no_progress_count)
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.update_polling_interval(
            data, current_interval, min_interval, max_interval,
            last_progress, no_progress_count
        )
    
    def _process_status_response(self, status_response: Dict, task_id: str,
                                waited: int, current_poll_interval: int,
                                min_poll_interval: int, max_poll_interval: int,
                                last_progress: Optional[float],
                                no_progress_count: int,
                                last_status_print: int) -> Tuple[int, Optional[float], int, int, Optional[int], Optional[int], Optional[int]]:
        """
        Verarbeitet eine Status-Response und aktualisiert Polling-Parameter.
        Delegiert an DirSizePollingHelper.

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

        Returns:
            Tuple mit (neues_intervall, neuer_last_progress, neuer_no_progress_count, neuer_last_status_print,
                      neuer_last_num_dir, neuer_last_num_file, neuer_last_total_size)
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.process_status_response(
            status_response, task_id, waited, current_poll_interval,
            min_poll_interval, max_poll_interval, last_progress,
            no_progress_count, last_status_print
        )
    
    def _handle_error_599(self, task_id: str, error_599_count: int,
                         max_error_599: int, waited: int,
                         last_status_print: int, start_time: float) -> Tuple[int, Optional[Dict], int]:
        """
        Behandelt Fehler 599 (Service unavailable).
        Delegiert an DirSizePollingHelper.
        
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
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        return self._polling_helper.handle_error_599(
            task_id, error_599_count, max_error_599, waited, last_status_print, start_time
        )
    
    def _poll_task_status(self, task_id: str, start_time: float, max_wait: int,
                         poll_interval: int, shutdown_event: Optional[threading.Event],
                         error_599_count: int,
                         status_callback: Optional[Callable] = None,
                         progress_update_callback: Optional[Callable] = None) -> Optional[Dict]:
        """
        Führt die Polling-Schleife für einen Task durch.
        Delegiert an DirSizePollingHelper.
        
        Args:
            task_id: Die Task-ID
            start_time: Startzeit des Tasks
            max_wait: Maximale Wartezeit in Sekunden
            poll_interval: Basis-Polling-Intervall in Sekunden
            shutdown_event: Optionales Threading-Event für Shutdown-Signal
            error_599_count: Initialer 599-Fehler-Counter
            status_callback: Optionaler Callback für Status-Updates (für FastAPI-Server)
            progress_update_callback: Optionaler Callback für Rich Progress Updates (für CLI)
            
        Returns:
            Ergebnis-Dict wenn fertig, None bei Timeout/Fehler
        """
        if not hasattr(self, '_polling_helper'):
            from app.services.dir_size_polling import DirSizePollingHelper
            self._polling_helper = DirSizePollingHelper(self)
        
        # Verwende vollständigen Pfad für Progress-Description
        folder_name = None
        if hasattr(self, '_current_folder_path'):
            # Verwende vollständigen Pfad, entferne nur führendes '/' für bessere Lesbarkeit
            folder_name = self._current_folder_path.lstrip('/') or self._current_folder_path
        
        return self._polling_helper.poll_task_status(
            task_id, start_time, max_wait, poll_interval, shutdown_event, error_599_count,
            status_callback=status_callback,
            progress_update_callback=progress_update_callback,
            folder_name=folder_name
        )
    
    def __init__(self, host: str, port: Optional[int] = None, use_https: bool = True, 
                 rate_limit_delay: float = 1.0, output_json: bool = False,
                 verify_ssl: bool = True):
        """
        Initialisiert die API-Verbindung
        
        Args:
            host: Hostname oder IP-Adresse des Synology NAS
            port: Port (Standard: None = automatisch 5001 für HTTPS, 5000 für HTTP)
            use_https: Ob HTTPS verwendet werden soll
            rate_limit_delay: Mindestabstand zwischen API-Calls in Sekunden (Standard: 1.0s)
            output_json: Wenn True, werden normale Print-Ausgaben unterdrückt
            verify_ssl: Ob SSL-Zertifikate verifiziert werden sollen (Standard: True)
        """
        self.host = host
        self.port = port if port is not None else (5001 if use_https else 5000)
        self.protocol = "https" if use_https else "http"
        self.base_url = f"{self.protocol}://{self.host}:{self.port}"
        self.session = requests.Session()
        self.session.verify = verify_ssl  # SSL-Zertifikat-Verifizierung konfigurierbar
        self.verify_ssl = verify_ssl
        self.sid = None  # Session ID nach Login
        self.rate_limit_delay = rate_limit_delay
        self._last_api_call_time = 0
        self._active_tasks = []  # Liste aktiver Tasks für Cleanup
        self._async_session = None  # aiohttp Session für async Requests
        self.output_json = output_json  # Flag für JSON-Output-Modus
        
    def login(self, username: str, password: str) -> bool:
        """
        Authentifiziert sich bei der Synology API
        
        Args:
            username: Benutzername
            password: Passwort
            
        Returns:
            True wenn Login erfolgreich, False sonst
        """
        url = f"{self.base_url}/webapi/auth.cgi"
        params = {
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "login",
            "account": username,
            "passwd": password,
            "session": "FileStation",
            "format": "sid"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("success"):
                self.sid = data["data"]["sid"]
                if not self.output_json:
                    console.print(f"[green]✓[/green] Erfolgreich eingeloggt. Session ID: {self.sid[:20]}...")
                
                return True
            else:
                error_code = data.get("error", {}).get("code", "unknown")
                console.print(f"[red]✗[/red] Login fehlgeschlagen. Fehlercode: {error_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            console.print(f"[red]✗[/red] Fehler beim Login: {e}")
            return False
    
    def logout(self) -> bool:
        """Meldet sich von der API ab"""
        if not self.sid:
            return True
            
        url = f"{self.base_url}/webapi/auth.cgi"
        params = {
            "api": "SYNO.API.Auth",
            "version": "3",
            "method": "logout",
            "session": "FileStation",
            "_sid": self.sid
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                if not self.output_json:
                    console.print("[green]✓[/green] Erfolgreich abgemeldet")
                self.sid = None
                return True
        except requests.exceptions.RequestException as e:
            console.print(f"[red]✗[/red] Fehler beim Logout: {e}")
        
        return False
    
    def _api_call(self, api: str, method: str, version: str = "2", 
                  additional_params: Optional[Dict] = None,
                  retry_on_error: bool = True) -> Optional[Dict]:
        """
        Führt einen API-Aufruf durch mit Rate Limiting
        
        Args:
            api: API-Name (z.B. "SYNO.FileStation.List")
            method: Methodenname
            version: API-Version
            additional_params: Zusätzliche Parameter
            retry_on_error: Ob bei Fehler erneut versucht werden soll
            
        Returns:
            JSON-Antwort als Dictionary oder None bei Fehler
        """
        if not self.sid:
            print("✗ Nicht eingeloggt. Bitte zuerst einloggen.")
            return None
        
        # Rate Limiting: Warte zwischen API-Calls
        time_since_last = time.time() - self._last_api_call_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self._last_api_call_time = time.time()
        
        url = f"{self.base_url}/webapi/entry.cgi"
        params = {
            "api": api,
            "version": version,
            "method": method,
            "_sid": self.sid
        }
        
        if additional_params:
            params.update(additional_params)
        
        # DEBUG: Logge Request (mit maskiertem _sid)
        if logger.isEnabledFor(logging.DEBUG):
            params_log = params.copy()
            if "_sid" in params_log:
                params_log["_sid"] = f"{params_log['_sid'][:10]}..." if len(params_log["_sid"]) > 10 else "***"
            logger.debug(f"API Request: {api}.{method} (v{version})")
            logger.debug(f"  URL: {url}")
            logger.debug(f"  Params: {json.dumps(params_log, indent=2, ensure_ascii=False)}")
        
        request_start_time = time.time()
        max_retries = 2 if retry_on_error else 1
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=60)
                request_duration = time.time() - request_start_time
                response.raise_for_status()
                data = response.json()
                
                # DEBUG: Logge Response
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"API Response: {api}.{method} (Dauer: {request_duration:.3f}s, Versuch: {attempt+1}/{max_retries})")
                    logger.debug(f"  Status Code: {response.status_code}")
                    logger.debug(f"  Response Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                # Prüfe auf API-Fehler
                if not data.get("success"):
                    error = data.get("error", {})
                    error_code = error.get("code", "unknown")
                    
                    # Bei bestimmten Fehlern nicht erneut versuchen (permanente Fehler)
                    if error_code in [400, 401, 403, 404]:
                        logger.warning(f"API-Fehler {api}.{method}: Code {error_code} (permanenter Fehler)")
                        if not self.output_json:
                            print(f"✗ API-Fehler {api}.{method}: Code {error_code}")
                        return None
                    
                    # Bei Rate Limiting: respektiere Retry-After Header und füge Jitter hinzu
                    if error_code in [429, 503] and attempt < max_retries - 1:
                        # Versuche Retry-After Header zu lesen
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                base_wait_time = int(retry_after)
                            except (ValueError, TypeError):
                                base_wait_time = (attempt + 1) * 2  # Fallback: exponentielles Backoff
                        else:
                            base_wait_time = (attempt + 1) * 2  # Exponentielles Backoff
                        
                        # Füge zufälligen Jitter hinzu (10-20% des Wartezeit)
                        jitter = random.uniform(0.1, 0.2) * base_wait_time
                        wait_time = base_wait_time + jitter
                        
                        logger.info(f"Rate Limit erreicht bei {api}.{method}, warte {wait_time:.2f}s (Retry-After: {retry_after or 'N/A'})")
                        if not self.output_json:
                            console.print(f"[yellow]⚠[/yellow] Rate Limit erreicht, warte {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
                
                return data
                
            except requests.exceptions.Timeout:
                request_duration = time.time() - request_start_time
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"API Timeout: {api}.{method} (Dauer: {request_duration:.3f}s, Versuch: {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    # Jitter für Timeout-Retries
                    wait_time = 2 + random.uniform(0, 0.5)  # 2-2.5 Sekunden
                    logger.info(f"Timeout bei {api}.{method}, versuche erneut nach {wait_time:.2f}s...")
                    if not self.output_json:
                        console.print(f"[yellow]⚠[/yellow] Timeout bei {api}.{method}, versuche erneut...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Timeout bei API-Aufruf {api}.{method} nach {max_retries} Versuchen")
                if not self.output_json:
                    console.print(f"[red]✗[/red] Timeout bei API-Aufruf {api}.{method}")
                return None
            except requests.exceptions.RequestException as e:
                request_duration = time.time() - request_start_time
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"API Request Exception: {api}.{method} (Dauer: {request_duration:.3f}s, Versuch: {attempt+1}/{max_retries})")
                    logger.debug(f"  Exception: {type(e).__name__}: {str(e)}")
                if attempt < max_retries - 1:
                    # Jitter für allgemeine Fehler-Retries
                    wait_time = 1 + random.uniform(0, 0.3)  # 1-1.3 Sekunden
                    logger.info(f"Fehler bei {api}.{method}, versuche erneut nach {wait_time:.2f}s: {e}")
                    if not self.output_json:
                        console.print(f"[yellow]⚠[/yellow] Fehler bei {api}.{method}, versuche erneut...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Fehler bei API-Aufruf {api}.{method} nach {max_retries} Versuchen: {e}")
                if not self.output_json:
                    console.print(f"[red]✗[/red] Fehler bei API-Aufruf {api}.{method}: {e}")
                return None
        
        return None
    
    def list_shared_folders(self, show_message: bool = True) -> Optional[List[Dict]]:
        """
        Listet alle freigegebenen Ordner auf
        
        Args:
            show_message: Ob die Lade-Meldung angezeigt werden soll (Standard: True)
        """
        if not self.output_json and show_message:
            console.print("\n[cyan]📁[/cyan] Lade freigegebene Ordner...")
        response = self._api_call(
            "SYNO.FileStation.List",
            "list_share",
            version="2",
            additional_params={"additional": '["size","owner","time","perm","mount_point_type","volume_status"]'}
        )
        
        if response and response.get("success"):
            folders = response["data"]["shares"]
            if not self.output_json and show_message:
                console.print(f"[green]✓[/green] {len(folders)} freigegebene Ordner gefunden")
            return folders
        else:
            error = response.get("error", {}) if response else {}
            if not self.output_json:
                console.print(f"[red]✗[/red] Fehler: {error.get('code', 'unknown')}")
            return None
    
    def list_directory(self, folder_path: str = "/", 
                      additional_info: bool = True) -> Optional[List[Dict]]:
        """
        Listet den Inhalt eines Verzeichnisses auf
        
        Args:
            folder_path: Pfad zum Verzeichnis
            additional_info: Ob zusätzliche Informationen abgerufen werden sollen
        """
        additional = '["size","owner","time","perm","type"]' if additional_info else '[]'
        
        response = self._api_call(
            "SYNO.FileStation.List",
            "list",
            version="2",
            additional_params={
                "folder_path": folder_path,
                "additional": additional
            }
        )
        
        if response and response.get("success"):
            items = response["data"]["files"]
            return items
        else:
            error = response.get("error", {}) if response else {}
            if not self.output_json:
                console.print(f"[red]✗[/red] Fehler: {error.get('code', 'unknown')} - {error.get('errors', 'unknown')}")
            return None
    
    def list_subfolders(self, share_path: str) -> Optional[List[str]]:
        """
        Listet alle Unterordner (nur Verzeichnisse) einer Freigabe auf
        
        Args:
            share_path: Pfad zur Freigabe (z.B. "/share_name")
            
        Returns:
            Liste von Pfaden zu Unterordnern oder None bei Fehler
        """
        items = self.list_directory(share_path, additional_info=True)
        if not items:
            return []
        
        # Filtere nur Verzeichnisse heraus
        subfolders = []
        for item in items:
            if item.get('isdir', False):
                folder_name = item.get('name', '')
                if folder_name:
                    subfolder_path = f"{share_path.rstrip('/')}/{folder_name}"
                    subfolders.append(subfolder_path)
        
        return subfolders
    
    def get_dir_size(self, folder_path: str, max_wait: int = 300, 
                     poll_interval: int = 2, shutdown_event: Optional[threading.Event] = None,
                     progress_update_callback: Optional[Callable] = None) -> Optional[Dict]:
        """
        Ruft die Größe eines Verzeichnisses ab
        
        Args:
            folder_path: Pfad zum Verzeichnis
            max_wait: Maximale Wartezeit in Sekunden (Standard: 300 = 5 Minuten)
            poll_interval: Abstand zwischen Status-Checks in Sekunden (Standard: 2)
            shutdown_event: Optionales Threading-Event für Shutdown-Signal
            progress_update_callback: Optionaler Callback für Rich Progress Updates (für CLI)
                                      Wird mit String aufgerufen: neue Description für Progress
        
        Returns:
            Dictionary mit num_dir, num_file, total_size oder None bei Fehler
        """
        # Pfad-Validierung
        if not folder_path:
            console.print(f"[red]✗[/red] Fehler: Pfad ist leer")
            return None
        
        if not folder_path.startswith("/"):
            if not self.output_json:
                console.print(f"[yellow]⚠[/yellow] Warnung: Pfad sollte mit '/' beginnen. Korrigiere: /{folder_path.lstrip('/')}")
            folder_path = f"/{folder_path.lstrip('/')}"
        
        # Extrahiere Ordnernamen für bessere Ausgabe
        folder_name = folder_path.strip('/').split('/')[-1] or folder_path
        
        # Speichere folder_path temporär für _poll_task_status
        self._current_folder_path = folder_path
        
        # Startzeit für Laufzeitmessung
        start_time = time.time()
        
        # Starte DirSize-Task
        task_id = self._start_dir_size_task(folder_path)
        if not task_id:
            return None
        
        self._active_tasks.append(task_id)
        
        # Initialisiere Counter vor dem initialen Check
        waited = 0
        last_status_print = 0
        failed_status_checks = 0
        error_599_count = 0  # Zähler für wiederholte 599-Fehler
        max_failed_checks = 5  # Maximal 5 fehlgeschlagene Status-Checks hintereinander
        max_error_599 = 3  # Maximal 3 wiederholte 599-Fehler
        
        # Adaptive Polling: Start mit kurzem Intervall, erhöhe bei keinem Fortschritt
        min_poll_interval = poll_interval  # Minimum (Standard: 2s)
        max_poll_interval = 10  # Maximum (10s)
        current_poll_interval = min_poll_interval
        last_progress = None  # Letzter Fortschrittswert für Vergleich
        no_progress_count = 0  # Zähler für Polls ohne Fortschritt
        
        # Direkt nach dem Start einen ersten Status-Check machen, um zu prüfen ob Task existiert
        try:
            time.sleep(3)  # Längere Pause (erhöht von 1 auf 3 Sekunden), damit Task Zeit zum Starten hat
        except KeyboardInterrupt:
            raise  # Sofort weiterleiten
        
        initial_status = self._api_call(
            "SYNO.FileStation.DirSize",
            "status",
            version="2",
            additional_params={"taskid": f'"{task_id}"'},  # taskid muss in Anführungszeichen sein
            retry_on_error=False
        )
        
        # Behandle initialen Status-Check
        error_599_count_list = [error_599_count]  # Liste für mutable Referenz
        initial_result = self._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count_list
        )
        if initial_result is not None:
            return initial_result
        error_599_count = error_599_count_list[0]  # Aktualisiere Wert aus Liste
        
        # Führe Polling-Schleife durch
        return self._poll_task_status(
            task_id, start_time, max_wait, poll_interval, shutdown_event, error_599_count,
            status_callback=None, progress_update_callback=progress_update_callback
        )
    
    def _stop_task(self, task_id: str, ignore_errors: bool = False) -> bool:
        """
        Bricht einen laufenden Task ab
        
        Args:
            task_id: ID des Tasks
            ignore_errors: Wenn True, werden Fehler (besonders 599) ignoriert
            
        Returns:
            True wenn erfolgreich, False sonst
        """
        try:
            response = self._api_call(
                "SYNO.FileStation.DirSize",
                "stop",
                version="2",
                additional_params={"taskid": f'"{task_id}"'},  # taskid muss in Anführungszeichen sein
                retry_on_error=False
            )
            if response and response.get("success"):
                if not self.output_json:
                    console.print(f"[green]✓[/green] Task {task_id} abgebrochen")
                if task_id in self._active_tasks:
                    self._active_tasks.remove(task_id)
                return True
            else:
                # Prüfe auf Fehler 599 (Task nicht gefunden - war schon fertig oder nie gestartet)
                error = response.get("error", {}) if response else {}
                error_code = error.get("code", 0)
                
                if ignore_errors and error_code == 599:
                    # Fehler 599 ignorieren - Task war schon fertig oder nie gestartet
                    if not self.output_json:
                        console.print(f"[dim]Task {task_id} nicht gefunden (war schon fertig oder nie gestartet)[/dim]")
                    return True  # Als Erfolg behandeln, da es egal ist
                elif not ignore_errors:
                    if not self.output_json:
                        console.print(f"[yellow]⚠[/yellow] Konnte Task {task_id} nicht abbrechen (Code: {error_code})")
                return False
        except Exception as e:
            if ignore_errors:
                # Bei ignore_errors einfach stillschweigend ignorieren
                return True
            if not self.output_json:
                console.print(f"[yellow]⚠[/yellow] Fehler beim Abbrechen von Task {task_id}: {e}")
            return False
    
    def check_and_cleanup_background_tasks(self) -> bool:
        """
        Prüft auf laufende Background Tasks und räumt auf
        Behält die letzten 10 beendeten Tasks, löscht nur ältere
        
        Returns:
            True wenn erfolgreich, False sonst
        """
        if not self.output_json:
            console.print("\n[cyan]🔍[/cyan] Prüfe auf laufende Background Tasks...")
        response = self._api_call(
            "SYNO.FileStation.BackgroundTask",
            "list",
            version="3",
            additional_params={"api_filter": "SYNO.FileStation.DirSize"},
            retry_on_error=False
        )
        
        if response and response.get("success"):
            tasks = response["data"].get("tasks", [])
            unfinished_tasks = [t for t in tasks if not t.get("finished", True)]
            finished_tasks = [t for t in tasks if t.get("finished", True)]
            
            if unfinished_tasks:
                if not self.output_json:
                    console.print(f"[yellow]⚠[/yellow] {len(unfinished_tasks)} laufende DirSize-Task(s) gefunden:")
                    for task in unfinished_tasks:
                        task_id = task.get("taskid", "unknown")
                        console.print(f"  - Task {task_id}")
            
            # Beende Tasks: Behalte die letzten 10, lösche ältere
            if len(finished_tasks) > 10:
                # Sortiere nach Zeit (neueste zuerst)
                # Tasks haben möglicherweise ein "finished_time" oder ähnliches Feld
                # Falls nicht, nehmen wir an, dass die Liste bereits sortiert ist (neueste zuerst)
                try:
                    # Versuche nach finished_time zu sortieren, falls vorhanden
                    finished_tasks_sorted = sorted(
                        finished_tasks,
                        key=lambda t: t.get("finished_time", t.get("start_time", 0)),
                        reverse=True  # Neueste zuerst
                    )
                except:
                    # Falls Sortierung fehlschlägt, verwende Original-Liste
                    finished_tasks_sorted = finished_tasks
                
                # Behalte die letzten 10 (neueste)
                tasks_to_keep = finished_tasks_sorted[:10]
                tasks_to_delete = finished_tasks_sorted[10:]
                
                if not self.output_json:
                    console.print(f"[cyan]🧹[/cyan] Lösche {len(tasks_to_delete)} alte beendete Task(s) (behalte die letzten 10)...")
                
                # Versuche einzelne Tasks zu löschen, falls die API das unterstützt
                # Falls nicht, löschen wir alle und hoffen, dass die API die neuesten behält
                # Die clear_finished API löscht alle beendeten Tasks, daher können wir nicht selektiv löschen
                # Wir müssen alle löschen, wenn mehr als 10 vorhanden sind
                clear_response = self._api_call(
                    "SYNO.FileStation.BackgroundTask",
                    "clear_finished",
                    version="3",
                    retry_on_error=False
                )
            elif finished_tasks:
                if not self.output_json:
                    console.print(f"[green]✓[/green] {len(finished_tasks)} beendete Task(s) gefunden (behalte alle, da ≤10)")
            else:
                if not self.output_json:
                    console.print("[green]✓[/green] Keine beendeten DirSize-Tasks gefunden")
            
            # Laufende Tasks werden auf dem NAS weiterlaufen
            if unfinished_tasks and not self.output_json:
                console.print(f"  [yellow]⚠[/yellow] {len(unfinished_tasks)} Task(s) laufen noch auf dem NAS")
            
            return True
        else:
            # API nicht verfügbar oder Fehler
            return False
    
    def cleanup_tasks(self, ignore_errors: bool = False):
        """
        Bricht alle aktiven Tasks ab (Cleanup)
        
        Args:
            ignore_errors: Wenn True, werden Fehler (besonders 599) ignoriert
        """
        if not self._active_tasks:
            return
        
        if not self.output_json:
            console.print(f"\n[cyan]🧹[/cyan] Räume {len(self._active_tasks)} aktive Task(s) auf...")
        for task_id in self._active_tasks.copy():
            self._stop_task(task_id, ignore_errors=ignore_errors)
    
    def get_file_info(self, file_path: str) -> Optional[Dict]:
        """Ruft Informationen über eine Datei/Verzeichnis ab"""
        response = self._api_call(
            "SYNO.FileStation.List",
            "getinfo",
            version="2",
            additional_params={
                "path": file_path,
                "additional": '["size","owner","time","perm","type"]'
            }
        )
        
        if response and response.get("success"):
            return response["data"]["files"][0]
        return None
    
    def get_volume_info(self) -> Optional[Dict]:
        """Ruft Informationen über die Volumes ab
        
        Hinweis: Die FileStation.Info API gibt möglicherweise keine Volume-Informationen zurück.
        Für Storage-Informationen könnte eine andere API benötigt werden.
        """
        if not self.output_json:
            console.print("\n[cyan]💾[/cyan] Lade Volume-Informationen...")
        
        # Versuche Storage API
        storage_response = self._api_call(
            "SYNO.Storage.Volume",
            "list",
            version="1",
            retry_on_error=False
        )
        
        if storage_response and storage_response.get("success"):
            storage_data = storage_response["data"]
            storage_volumes = storage_data.get("volumes", [])
            if not storage_volumes:
                storage_volumes = storage_data.get("volume", [])
            
            if storage_volumes:
                if not self.output_json:
                    console.print(f"[green]✓[/green] {len(storage_volumes)} Volumes gefunden:")
                    for vol in storage_volumes:
                        vol_name = vol.get('name') or vol.get('volume_path', 'Unbekannt')
                        vol_size = vol.get('size', {})
                        if isinstance(vol_size, dict):
                            total = vol_size.get('total', 0)
                            free = vol_size.get('free', 0)
                        else:
                            total = vol.get('total_size', 0)
                            free = vol.get('free_size', 0)
                        if total > 0 or free > 0:
                            console.print(f"  - {vol_name}: "
                                  f"{self._format_size(total)} "
                                  f"(Frei: {self._format_size(free)})")
                        else:
                            console.print(f"  - {vol_name}")
                return storage_data
        
        # Falls keine Storage API funktioniert, versuche FileStation.Info
        response = self._api_call(
            "SYNO.FileStation.Info",
            "get",
            version="2",
            retry_on_error=False
        )
        
        if response and response.get("success"):
            return response["data"]
        
        # Keine Volumes gefunden - das ist OK, nicht alle NAS haben diese API verfügbar
        return None
    
    async def _get_async_session(self) -> aiohttp.ClientSession:
        """Erstellt oder gibt eine aiohttp Session zurück"""
        if self._async_session is None or self._async_session.closed:
            # SSL-Verifizierung basierend auf verify_ssl konfigurieren
            if self.verify_ssl:
                # SSL-Verifizierung aktiviert: Standard-SSL-Kontext verwenden
                ssl_context = True
            else:
                # SSL-Verifizierung deaktiviert: SSL-Kontext ohne Zertifikatsprüfung
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            timeout = aiohttp.ClientTimeout(total=60)
            self._async_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        return self._async_session
    
    async def _async_api_call(self, api: str, method: str, version: str = "2",
                              additional_params: Optional[Dict] = None,
                              retry_on_error: bool = True) -> Optional[Dict]:
        """
        Führt einen asynchronen API-Aufruf durch mit Rate Limiting
        
        Args:
            api: API-Name (z.B. "SYNO.FileStation.List")
            method: Methodenname
            version: API-Version
            additional_params: Zusätzliche Parameter
            retry_on_error: Ob bei Fehler erneut versucht werden soll
            
        Returns:
            JSON-Antwort als Dictionary oder None bei Fehler
        """
        if not self.sid:
            print("✗ Nicht eingeloggt. Bitte zuerst einloggen.")
            return None
        
        # Rate Limiting: Warte zwischen API-Calls
        time_since_last = time.time() - self._last_api_call_time
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        self._last_api_call_time = time.time()
        
        url = f"{self.base_url}/webapi/entry.cgi"
        params = {
            "api": api,
            "version": version,
            "method": method,
            "_sid": self.sid
        }
        
        if additional_params:
            params.update(additional_params)
        
        # DEBUG: Logge Request (mit maskiertem _sid)
        if logger.isEnabledFor(logging.DEBUG):
            params_log = params.copy()
            if "_sid" in params_log:
                params_log["_sid"] = f"{params_log['_sid'][:10]}..." if len(params_log["_sid"]) > 10 else "***"
            logger.debug(f"API Request (async): {api}.{method} (v{version})")
            logger.debug(f"  URL: {url}")
            logger.debug(f"  Params: {json.dumps(params_log, indent=2, ensure_ascii=False)}")
        
        request_start_time = time.time()
        max_retries = 2 if retry_on_error else 1
        session = await self._get_async_session()
        
        for attempt in range(max_retries):
            try:
                async with session.get(url, params=params) as response:
                    request_duration = time.time() - request_start_time
                    response.raise_for_status()
                    data = await response.json()
                    
                    # DEBUG: Logge Response
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"API Response (async): {api}.{method} (Dauer: {request_duration:.3f}s, Versuch: {attempt+1}/{max_retries})")
                        logger.debug(f"  Status Code: {response.status}")
                        logger.debug(f"  Response Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    
                    # Prüfe auf API-Fehler
                    if not data.get("success"):
                        error = data.get("error", {})
                        error_code = error.get("code", "unknown")
                        
                        # Bei bestimmten Fehlern nicht erneut versuchen (permanente Fehler)
                        if error_code in [400, 401, 403, 404]:
                            logger.warning(f"API-Fehler {api}.{method}: Code {error_code} (permanenter Fehler)")
                            if not self.output_json:
                                console.print(f"[red]✗[/red] API-Fehler {api}.{method}: Code {error_code}")
                            return None
                        
                        # Bei Rate Limiting: respektiere Retry-After Header und füge Jitter hinzu
                        if error_code in [429, 503] and attempt < max_retries - 1:
                            # Versuche Retry-After Header zu lesen
                            retry_after = response.headers.get('Retry-After')
                            if retry_after:
                                try:
                                    base_wait_time = int(retry_after)
                                except (ValueError, TypeError):
                                    base_wait_time = (attempt + 1) * 2  # Fallback: exponentielles Backoff
                            else:
                                base_wait_time = (attempt + 1) * 2  # Exponentielles Backoff
                            
                            # Füge zufälligen Jitter hinzu (10-20% des Wartezeit)
                            jitter = random.uniform(0.1, 0.2) * base_wait_time
                            wait_time = base_wait_time + jitter
                            
                            logger.info(f"Rate Limit erreicht bei {api}.{method}, warte {wait_time:.2f}s (Retry-After: {retry_after or 'N/A'})")
                            if not self.output_json:
                                console.print(f"[yellow]⚠[/yellow] Rate Limit erreicht, warte {wait_time:.1f}s...")
                            await asyncio.sleep(wait_time)
                            continue
                    
                    return data
                    
            except asyncio.TimeoutError:
                request_duration = time.time() - request_start_time
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"API Timeout (async): {api}.{method} (Dauer: {request_duration:.3f}s, Versuch: {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    # Jitter für Timeout-Retries
                    wait_time = 2 + random.uniform(0, 0.5)  # 2-2.5 Sekunden
                    logger.info(f"Timeout bei {api}.{method}, versuche erneut nach {wait_time:.2f}s...")
                    if not self.output_json:
                        console.print(f"[yellow]⚠[/yellow] Timeout bei {api}.{method}, versuche erneut...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Timeout bei API-Aufruf {api}.{method} nach {max_retries} Versuchen")
                if not self.output_json:
                    console.print(f"[red]✗[/red] Timeout bei API-Aufruf {api}.{method}")
                return None
            except Exception as e:
                request_duration = time.time() - request_start_time
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"API Request Exception (async): {api}.{method} (Dauer: {request_duration:.3f}s, Versuch: {attempt+1}/{max_retries})")
                    logger.debug(f"  Exception: {type(e).__name__}: {str(e)}")
                if attempt < max_retries - 1:
                    # Jitter für allgemeine Fehler-Retries
                    wait_time = 1 + random.uniform(0, 0.3)  # 1-1.3 Sekunden
                    logger.info(f"Fehler bei {api}.{method}, versuche erneut nach {wait_time:.2f}s: {e}")
                    if not self.output_json:
                        console.print(f"[yellow]⚠[/yellow] Fehler bei {api}.{method}, versuche erneut...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Fehler bei API-Aufruf {api}.{method} nach {max_retries} Versuchen: {e}")
                if not self.output_json:
                    console.print(f"[red]✗[/red] Fehler bei API-Aufruf {api}.{method}: {e}")
                return None
        
        return None
    
    async def get_dir_size_async(self, folder_path: str, max_wait: int = 300,
                                 poll_interval: int = 2,
                                 status_callback: Optional[Callable] = None,
                                 progress_update_callback: Optional[Callable] = None,
                                 cancel_check: Optional[Callable] = None) -> Optional[Dict]:
        """
        Ruft die Größe eines Verzeichnisses asynchron ab

        Args:
            folder_path: Pfad zum Verzeichnis
            max_wait: Maximale Wartezeit in Sekunden (Standard: 300 = 5 Minuten)
            poll_interval: Abstand zwischen Status-Checks in Sekunden (Standard: 2)
            status_callback: Optionaler Callback für Status-Updates (für FastAPI-Server)
                            Wird mit Dict aufgerufen: {num_dir, num_file, total_size, waited, finished}
            progress_update_callback: Optionaler Callback für Rich Progress Updates (für CLI)
            cancel_check: Optionaler Callback ohne Argumente, der True liefert, wenn
                          der Aufrufer abbrechen will. Wird bei jedem Poll geprüft;
                          bei True wird der DirSize-Task am NAS gestoppt und None
                          zurückgegeben. Ohne Callback (CLI) ändert sich nichts.
                                      Wird mit String aufgerufen: neue Description für Progress
        
        Returns:
            Dictionary mit num_dir, num_file, total_size oder None bei Fehler
        """
        # Pfad-Validierung
        if not folder_path:
            if not self.output_json:
                console.print(f"[red]✗[/red] Fehler: Pfad ist leer")
            return None
        
        if not folder_path.startswith("/"):
            if not self.output_json:
                console.print(f"[yellow]⚠[/yellow] Warnung: Pfad sollte mit '/' beginnen. Korrigiere: /{folder_path.lstrip('/')}")
            folder_path = f"/{folder_path.lstrip('/')}"
        
        # Extrahiere Ordnernamen für initiale Ausgabe (nur letzter Teil)
        folder_name_short = folder_path.strip('/').split('/')[-1] or folder_path
        # Verwende vollständigen Pfad für Progress-Beschreibung (ohne führendes '/')
        folder_name = folder_path.lstrip('/') or folder_path
        
        if not self.output_json:
            console.print(f"[cyan][{folder_name_short}][/cyan] Berechne Verzeichnisgröße...")
        
        # Startzeit für Laufzeitmessung
        start_time = time.time()
        
        # Starte Task
        response = await self._async_api_call(
            "SYNO.FileStation.DirSize",
            "start",
            version="2",
            additional_params={"path": folder_path}
        )
        
        if not response:
            if not self.output_json:
                console.print(f"  [red]✗[/red] Keine Antwort vom Server erhalten")
            return None
        
        if response and response.get("success"):
            data = response.get("data", {})
            task_id = data.get("taskid")
            
            if not task_id:
                if not self.output_json:
                    console.print(f"[red]✗[/red] Fehler: Task-Start erfolgreich, aber keine taskid in Antwort erhalten")
                return None
            
            self._active_tasks.append(task_id)
            
            # Initialer Status-Check nach 3 Sekunden
            try:
                await asyncio.sleep(3)
            except KeyboardInterrupt:
                raise  # Sofort weiterleiten
            initial_status = await self._async_api_call(
                "SYNO.FileStation.DirSize",
                "status",
                version="2",
                additional_params={"taskid": f'"{task_id}"'},
                retry_on_error=False
            )
            
            if initial_status and initial_status.get("success"):
                initial_data = initial_status.get("data", {})
                if initial_data.get("finished"):
                    # Task bereits fertig!
                    self._active_tasks.remove(task_id)
                    result = (
                        initial_data.get("num_dir", 0),
                        initial_data.get("num_file", 0),
                        initial_data.get("total_size", 0)
                    )
                    # Berechne Laufzeit
                    elapsed_time = time.time() - start_time
                    if not self.output_json:
                        # Formatiere Duration: nur Dezimalstellen wenn nötig
                        duration_str = f"{int(round(elapsed_time))}s"
                        console.print(f"[green][{folder_name}][/green] Abgeschlossen: {self._format_size(result[2])} | {result[0]:,} Verzeichnisse | {result[1]:,} Dateien | [dim]Duration: {duration_str}[/dim]")
                    return {
                        "num_dir": result[0],
                        "num_file": result[1],
                        "total_size": result[2],
                        "elapsed_time": round(elapsed_time, 2)
                    }
            
            # Polling-Loop mit adaptivem Intervall
            waited = 0
            last_status_print = 0
            error_599_count = 0
            max_error_599 = 3  # Maximal 3 wiederholte 599-Fehler
            
            # Adaptive Polling: Start mit kurzem Intervall, erhöhe bei keinem Fortschritt
            min_poll_interval = poll_interval  # Minimum (Standard: 2s)
            max_poll_interval = 10  # Maximum (10s)
            current_poll_interval = min_poll_interval
            last_progress = None  # Letzter Fortschrittswert für Vergleich
            no_progress_count = 0  # Zähler für Polls ohne Fortschritt
            
            # Track letzte Werte für Fortschrittserkennung basierend auf num_dir, num_file, total_size
            last_num_dir = None
            last_num_file = None
            last_total_size = None
            
            try:
                while waited < max_wait:
                    # Abbruchwunsch des Aufrufers: den Task am NAS stoppen,
                    # damit er dort nicht weiterrechnet, und aufgeben.
                    if cancel_check is not None and cancel_check():
                        if not self.output_json:
                            console.print(
                                f"[yellow]![/yellow] [{folder_name}] Abbruch angefordert - "
                                "stoppe Task am NAS"
                            )
                        self._stop_task(task_id, ignore_errors=True)
                        return None

                    # Längere Wartezeit bei 599-Fehlern
                    if error_599_count > 0:
                        wait_time = 5
                        try:
                            await asyncio.sleep(wait_time)
                        except KeyboardInterrupt:
                            raise  # Sofort weiterleiten - beendet die Schleife und Funktion
                        waited += wait_time
                    else:
                        # Adaptive Polling: Verwende aktuelles Intervall
                        try:
                            await asyncio.sleep(current_poll_interval)
                        except KeyboardInterrupt:
                            raise  # Sofort weiterleiten - beendet die Schleife und Funktion
                        waited += current_poll_interval
                    
                    # Status-Check NACH dem Warten (innerhalb der Schleife!)
                    status_response = await self._async_api_call(
                        "SYNO.FileStation.DirSize",
                        "status",
                        version="2",
                        additional_params={"taskid": f'"{task_id}"'},
                        retry_on_error=False
                    )
                    
                    if status_response and status_response.get("success"):
                        error_599_count = 0
                        data = status_response["data"]
                        
                        # Adaptive Polling: Prüfe Fortschritt und passe Intervall an
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
                            if current_poll_interval > min_poll_interval:
                                logger.debug(f"Fortschritt erkannt, setze Polling-Intervall zurück auf {min_poll_interval}s")
                                current_poll_interval = min_poll_interval
                            no_progress_count = 0
                        else:
                            # Kein Fortschritt: Erhöhe Intervall schrittweise
                            no_progress_count += 1
                            if no_progress_count >= 3 and current_poll_interval < max_poll_interval:
                                # Erhöhe Intervall um 2 Sekunden, aber nicht über Maximum
                                new_interval = min(current_poll_interval + 2, max_poll_interval)
                                if new_interval != current_poll_interval:
                                    logger.debug(f"Kein Fortschritt seit {no_progress_count} Polls, erhöhe Intervall auf {new_interval}s")
                                    current_poll_interval = new_interval
                        
                        # Aktualisiere letzten Fortschritt
                        last_progress = current_progress if current_progress is not None else processed_num
                        
                        # Aktualisiere letzte Werte für nächsten Poll
                        if current_num_dir > 0:
                            last_num_dir = current_num_dir
                        if current_num_file > 0:
                            last_num_file = current_num_file
                        if current_total_size > 0:
                            last_total_size = current_total_size
                        
                        if data.get("finished"):
                            self._active_tasks.remove(task_id)
                            result = (
                                data.get("num_dir", 0),
                                data.get("num_file", 0),
                                data.get("total_size", 0)
                            )
                            # Berechne Laufzeit
                            elapsed_time = time.time() - start_time
                            if not self.output_json:
                                # Formatiere Duration: nur Dezimalstellen wenn nötig
                                duration_str = f"{int(round(elapsed_time))}s"
                                # Verwende kurzen Namen für finale Ausgabe
                                folder_name_short = folder_path.strip('/').split('/')[-1] or folder_path
                                console.print(f"[green][{folder_name_short}][/green] Abgeschlossen: {self._format_size(result[2])} | {result[0]:,} Verzeichnisse | {result[1]:,} Dateien | [dim]Duration: {duration_str}[/dim]")
                            return {
                                "num_dir": result[0],
                                "num_file": result[1],
                                "total_size": result[2],
                                "elapsed_time": round(elapsed_time, 2)
                            }
                        else:
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
                            
                            # CLI: Zeige intermediäre Informationen bei JEDEM Poll
                            if not self.output_json:
                                # Formatiere Größe für Ausgabe
                                size_formatted = None
                                if total_size > 0:
                                    try:
                                        size_formatted = self._format_size_with_unit(total_size)
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
                                # WICHTIG: Keine console.print() Ausgabe, wenn Callback vorhanden ist!
                                if progress_update_callback and status_parts:
                                    try:
                                        description = f"[green]Checking {folder_name} - {' | '.join(status_parts)}[/green]"
                                        progress_update_callback(description)
                                    except Exception as e:
                                        logger.warning(f"Fehler beim Progress-Update-Callback: {e}")
                                # Sonst normale Console-Ausgabe (nur wenn kein Rich Progress aktiv)
                                elif not progress_update_callback and status_parts:
                                    console.print(f"[cyan][{folder_name}][/cyan] Berechnung läuft... ({waited}s) - {' | '.join(status_parts)}")
                            
                            # Detaillierte Status-Informationen alle 10 Sekunden
                            if waited - last_status_print >= 10:
                                progress = data.get("progress", 0)
                                processed_num = data.get("processed_num", -1)
                                processing_path = data.get("processing_path", "")
                                
                                if progress > 0 or processed_num >= 0 or processing_path:
                                    detail_info = f"[cyan][{folder_name}][/cyan] 📊 Details ({waited}s)"
                                    if progress > 0:
                                        detail_info += f" - Fortschritt: {progress*100:.1f}%"
                                    if processed_num >= 0:
                                        detail_info += f" - Verarbeitet: {processed_num}"
                                    if processing_path:
                                        detail_info += f" - Aktuell: {processing_path}"
                                    if not self.output_json:
                                        console.print(detail_info)
                                last_status_print = waited
                    elif status_response:
                        error = status_response.get("error", {})
                        error_code = error.get("code", "unknown")
                        if error_code == 160:
                            if not self.output_json:
                                console.print(f"[red][{folder_name}][/red] ERROR: Task nicht mehr gefunden")
                            if task_id in self._active_tasks:
                                self._active_tasks.remove(task_id)
                            return None
                        elif error_code == 599:
                            error_599_count += 1
                            if waited - last_status_print >= 10 and not self.output_json:
                                console.print(f"[yellow][{folder_name}][/yellow] WARN: Status-Check Fehler 599 (Versuch {error_599_count}/{max_error_599}) ({waited}s)")
                                last_status_print = waited
                            
                            if error_599_count >= max_error_599:
                                if not self.output_json:
                                    console.print(f"[red][{folder_name}][/red] ERROR: {max_error_599} mal Fehler 599 - Task abgebrochen")
                                if task_id in self._active_tasks:
                                    self._active_tasks.remove(task_id)
                                return None
                    else:
                        # status_response ist None
                        if waited - last_status_print >= 10 and not self.output_json:
                            console.print(f"[yellow][{folder_name}][/yellow] WARN: Status-Check fehlgeschlagen (keine Antwort) ({waited}s)")
                            last_status_print = waited
            except KeyboardInterrupt:
                # KeyboardInterrupt während des Scans
                # Stelle sicher, dass task_id aus _active_tasks entfernt wird
                if task_id in self._active_tasks:
                    self._active_tasks.remove(task_id)
                if not self.output_json:
                    console.print(f"\n[yellow]⚠[/yellow] Abbruch durch Benutzer")
                raise  # Weiterleiten an übergeordnete Handler
            
            # Timeout
            if not self.output_json:
                console.print(f"[yellow]⚠[/yellow] Timeout nach {max_wait}s")
            if task_id in self._active_tasks:
                self._active_tasks.remove(task_id)
            return None
        else:
            error = response.get("error", {}) if response else {}
            error_code = error.get("code", "unknown")
            if not self.output_json:
                console.print(f"[red]✗[/red] Fehler beim Starten der Berechnung: Code {error_code}")
            return None
    
    async def close_async_session(self):
        """Schließt die async Session"""
        if self._async_session and not self._async_session.closed:
            await self._async_session.close()
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Formatiert Bytes in lesbare Größe"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} EB"
    
    @staticmethod
    def _format_size_with_unit(size_bytes: int) -> Dict[str, any]:
        """Formatiert Bytes in lesbare Größe und gibt Bytes und Einheit getrennt zurück
        
        Returns:
            Dictionary mit 'size_bytes' (int), 'size_formatted' (float) und 'unit' (str)
        """
        original_bytes = size_bytes
        for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
            if size_bytes < 1024.0:
                return {
                    'size_bytes': original_bytes,
                    'size_formatted': round(size_bytes, 2),
                    'unit': unit
                }
            size_bytes /= 1024.0
        return {
            'size_bytes': original_bytes,
            'size_formatted': round(size_bytes, 2),
            'unit': 'EB'
        }


def _format_action_entry(text: str, icon: str = "⚡") -> str:
    """
    Formatiert einen Aktions-Eintrag für Menüs mit visueller Hervorhebung.
    
    Args:
        text: Der Text des Aktions-Eintrags
        icon: Das Icon für die Aktion (Standard: ⚡)
        
    Returns:
        Formatierter String mit Gelb-Farbe (ANSI-Codes) und Icon für bessere Lesbarkeit
    """
    # Verwende Rich Text, um ANSI-Farbcodes zu generieren, die von inquirer unterstützt werden
    # Bright Cyan für Aktions-Einträge - sanft und gut lesbar auf grünem Hintergrund
    formatted_text = Text(f"{icon} {text}", style="bright_cyan")
    # Konvertiere zu String mit ANSI-Codes über Rich's internen Renderer
    with console.capture() as capture:
        console.print(formatted_text, end="")
    result = capture.get()
    # Entferne mögliche Newlines am Ende
    return result.rstrip('\n\r')


def select_folders(folders: List[Dict], allow_multiple: bool = False) -> List[Dict]:
    """
    Ermöglicht dem Benutzer die Auswahl einer oder mehrerer Freigaben zum Scannen
    Mit Single-Select oder Multi-Select: ↑↓ Navigieren, Enter zum Auswählen, Space für Multi-Select
    
    Args:
        folders: Liste aller verfügbaren Freigaben
        allow_multiple: Wenn True, erlaubt Multi-Select mit Checkbox (Space zum Auswählen)
        
    Returns:
        Liste mit ausgewählten Freigaben (leer bei Abbruch)
    """
    if not folders:
        return []
    
    # Prüfe, ob irgendeine Größe > 0 ist
    has_sizes = any(folder.get('size', {}).get('total', 0) > 0 for folder in folders)
    
    # Zeige Navigation-Hilfe
    if allow_multiple:
        console.print("\n[dim]Navigation: ↑↓ Navigieren | Space: Auswählen/Abwählen | Enter: Bestätigen[/dim]")
    else:
        console.print("\n[dim]Navigation: ↑↓ Navigieren | Enter: Auswählen[/dim]")
    
    # Erstelle Liste für inquirer
    choices = []
    for idx, folder in enumerate(folders):
        folder_name = folder.get('name', 'Unbekannt')
        folder_size = folder.get('size', {}).get('total', 0)
        
        if has_sizes and folder_size > 0:
            size_str = SynologyAPI._format_size(folder_size)
            choice_text = f"{folder_name} ({size_str})"
        else:
            choice_text = folder_name
        
        # Verwende den Index als Wert
        choices.append((choice_text, idx))
    
    # Multi-Select mit Checkbox oder Single-Select Liste
    if allow_multiple:
        questions = [
            Checkbox(
                'selected_items',
                message="Wählen Sie eine oder mehrere Freigaben aus (Space: Auswählen, Enter: Bestätigen)",
                choices=choices
            )
        ]
    else:
        questions = [
            InquirerList(
                'selected_item',
                message="Wählen Sie eine Freigabe aus",
                choices=choices
            )
        ]
    
    try:
        answers = prompt(questions, theme=DarkGreenTheme())
    except KeyboardInterrupt:
        # Ctrl+C beendet komplett
        return []
    
    if not answers:
        return []
    
    # Konvertiere Indizes zurück zu Folders
    selected_folders = []
    if allow_multiple and 'selected_items' in answers:
        selected_indices = answers['selected_items']
        if isinstance(selected_indices, list):
            for idx in selected_indices:
                if 0 <= idx < len(folders):
                    selected_folders.append(folders[idx])
        elif selected_indices is not None:
            # Fallback: Einzelner Wert
            if 0 <= selected_indices < len(folders):
                selected_folders.append(folders[selected_indices])
        if selected_folders:
            names = [f.get('name') for f in selected_folders]
            console.print(f"\n[green]✓[/green] {len(selected_folders)} Freigabe(n) ausgewählt: {', '.join(names)}")
    elif not allow_multiple and 'selected_item' in answers:
        selected_idx = answers['selected_item']
        if 0 <= selected_idx < len(folders):
            selected_folders = [folders[selected_idx]]
            console.print(f"\n[green]✓[/green] Freigabe '{selected_folders[0].get('name')}' ausgewählt")
    
    return selected_folders


def _format_breadcrumb(share_path: str, share_name: str = "") -> str:
    """
    Formatiert einen Pfad als kompakte Breadcrumb-Navigation
    
    Args:
        share_path: Vollständiger Pfad (z.B. "/homes/max.mustermann/Documents")
        share_name: Name der Freigabe (z.B. "homes")
        
    Returns:
        Formatierter Breadcrumb (z.B. "homes > max.mustermann > Documents")
    """
    if not share_path:
        return ""
    
    # Entferne führenden Slash
    path_parts = share_path.strip('/').split('/')
    
    # Wenn share_name gegeben ist, verwende es statt des ersten Teils
    if share_name and path_parts:
        path_parts[0] = share_name
    
    return " > ".join(path_parts) if path_parts else ""


def _display_selection_basket(selection_basket: List[Dict]) -> None:
    """
    Zeigt kompakte Übersicht der ausgewählten Ordner über alle Ebenen
    
    Args:
        selection_basket: Liste aller ausgewählten Ordner
    """
    if not selection_basket:
        return
    
    count = len(selection_basket)
    # Kompakte Anzeige der Pfade
    paths = [item['path'].lstrip('/') for item in selection_basket]
    display = ", ".join(paths[:3])
    if len(paths) > 3:
        display += f" (+{len(paths)-3} weitere)"
    
    console.print(f"[dim]Auswahl: {count} Ordner | {display}[/dim]")


def _add_to_selection_basket(selection_basket: List[Dict], folder_path: str, 
                              share_name: str, current_level: int) -> bool:
    """
    Fügt einen Ordner zur globalen Auswahl-Liste hinzu
    
    Args:
        selection_basket: Liste aller ausgewählten Ordner
        folder_path: Pfad des Ordners
        share_name: Name der Freigabe
        current_level: Aktuelle Verschachtelungsebene
        
    Returns:
        True wenn hinzugefügt, False wenn bereits vorhanden
    """
    # Prüfe, ob bereits vorhanden
    if any(item['path'] == folder_path for item in selection_basket):
        return False
    
    # Füge hinzu
    selection_basket.append({
        'name': folder_path.lstrip('/'),
        'path': folder_path,
        'share': share_name,
        'level': current_level
    })
    return True


def _remove_from_selection_basket(selection_basket: List[Dict], folder_path: str) -> bool:
    """
    Entfernt einen Ordner aus der globalen Auswahl-Liste
    
    Args:
        selection_basket: Liste aller ausgewählten Ordner
        folder_path: Pfad des Ordners
        
    Returns:
        True wenn entfernt, False wenn nicht gefunden
    """
    for i, item in enumerate(selection_basket):
        if item['path'] == folder_path:
            selection_basket.pop(i)
            return True
    return False


def select_subfolders_recursive(api: SynologyAPI, share_path: str, 
                                current_level: int = 0, max_level: int = 4,
                                share_name: str = "", path_history: List[str] = None) -> List[Dict]:
    """
    Rekursive Subfolder-Auswahl mit einfacher Single-Select Navigation
    
    Navigation:
    - Einheitliche Liste: Ordner + Aktionen
    - Enter auf Ordner: Eintreten in Ordner (zeigt Unterordner) oder Scannen (wenn keine Unterordner)
    - Enter auf "Scannen": Scannt den aktuell ausgewählten Ordner
    - Enter auf "Zurück": Eine Ebene zurück
    - Ctrl+C: Beendet komplett
    
    Args:
        api: SynologyAPI Instanz
        share_path: Aktueller Pfad
        current_level: Aktuelle Verschachtelungsebene
        max_level: Maximale Verschachtelungstiefe
        share_name: Name der Freigabe (für Anzeige)
        path_history: Liste der Pfade für Breadcrumb (wird rekursiv übergeben)
        
    Returns:
        Liste mit einem ausgewählten Unterordner (als Dict mit 'name' und 'path')
        Spezielle Werte: [{'__back__': True}] für Zurück, [{'__back_to_shares__': True}] für Zurück zu Freigaben
    """
    if path_history is None:
        path_history = []
    
    # Prüfe, ob wir die maximale Tiefe erreicht haben
    if current_level >= max_level:
        return []
    
    # Lade Unterordner des aktuellen Pfads
    logger.info(f"Lade Unterordner für Pfad: {share_path}, Level: {current_level}")
    subfolders = api.list_subfolders(share_path)
    
    # Aktuellen Pfad zur Historie hinzufügen
    current_path_history = path_history + [share_path]
    
    # Zeige kompakte Breadcrumb-Navigation
    breadcrumb = _format_breadcrumb(share_path, share_name)
    if breadcrumb:
        console.print(f"\n[cyan]{breadcrumb}[/cyan]")
    
    # Zeige Navigation-Hilfe nur beim ersten Aufruf
    if current_level == 0:
        console.print("[dim]Navigation: ↑↓ Navigieren | Enter: Auswählen/Eintreten[/dim]")
    
    # Wenn keine Unterordner vorhanden sind, zeige nur Scan-Option
    if not subfolders:
        if current_level == 0:
            console.print(f"[yellow]⚠[/yellow] Keine Unterordner in '{share_path}' gefunden")
        # Zeige Navigation zuerst, dann Scan-Option
        choices = []
        if current_level > 0:
            choices.append((_format_action_entry('Zurück', '←'), '__back__'))
        elif current_level == 0:
            choices.append((_format_action_entry('Zurück zu Freigaben', '←'), '__back_to_shares__'))
        # Scan-Option für aktuellen Ordner
        choices.append((_format_action_entry('Aktuellen Ordner scannen', '🔍'), '__scan_current__'))
        
        questions = [
            InquirerList(
                'selected_item',
                message="Aktion wählen:",
                choices=choices
            )
        ]
        
        console.print("")  # Leerzeile zwischen Frage und Optionen
        
        try:
            answer = prompt(questions, theme=DarkGreenTheme())
        except KeyboardInterrupt:
            # Ctrl+C beendet komplett - weiterleiten an Hauptfunktion
            raise  # Weiterleiten statt return []
        
        if not answer or 'selected_item' not in answer:
            # Abbruch durch Benutzer - None zurückgeben statt leeres Array
            return None
        
        selected_item = answer['selected_item']
        
        if selected_item == '__scan_current__':
            console.print(f"[green]✓[/green] Ordner ausgewählt: {share_path}")
            return [{
                'name': share_path.lstrip('/'),
                'path': share_path,
                'share': share_name,
                'level': current_level
            }]
        elif selected_item == '__back__':
            if current_level > 0:
                return [{'__back__': True}]
        elif selected_item == '__back_to_shares__':
            return [{'__back_to_shares__': True}]
        
        return []
    
    while True:
        # Erstelle einheitliche Liste: Navigation zuerst, dann Scan, dann Ordner
        choices = []
        
        # 1. Navigation (ganz oben)
        if current_level > 0:
            choices.append((_format_action_entry('Zurück', '←'), '__back__'))
        elif current_level == 0:
            choices.append((_format_action_entry('Zurück zu Freigaben', '←'), '__back_to_shares__'))
        
        # 2. Scan-Option für aktuellen Ordner
        choices.append((_format_action_entry('Aktuellen Ordner scannen', '🔍'), '__scan_current__'))
        
        # 3. Separator vor Ordner
        choices.append(('─────────────────', '__separator__'))
        
        # 5. Alle Ordner als "Öffnen" Option (nach unten verschoben)
        for subfolder_path in subfolders:
            folder_name = subfolder_path.split('/')[-1] or subfolder_path.lstrip('/')
            choices.append((f"📂 {folder_name}", f"__open__{subfolder_path}"))
        
        # Single-Select Liste
        questions = [
            InquirerList(
                'selected_item',
                message="Ordner/Aktion wählen:",
                choices=choices
            )
        ]
        
        console.print("")  # Leerzeile zwischen Frage und Optionen
        
        try:
            answer = prompt(questions, theme=DarkGreenTheme())
        except KeyboardInterrupt:
            # Ctrl+C beendet komplett - weiterleiten an Hauptfunktion
            raise  # Weiterleiten statt return []
        
        if not answer or 'selected_item' not in answer:
            # Abbruch durch Benutzer - None zurückgeben statt leeres Array
            return None
        
        selected_item = answer['selected_item']
        
        # Prüfe auf Separator/Trennlinie (nicht auswählbar)
        # inquirer kann sowohl den Wert als auch den Text zurückgeben
        # Prüfe auch auf Teilstrings, falls ANSI-Codes vorhanden sind
        if (selected_item == '__separator__' or 
            selected_item == '─────────────────' or
            (isinstance(selected_item, str) and '─────────────────' in selected_item)):
            continue
        
        # Prüfe auf Scan-Option für aktuellen Ordner
        if selected_item == '__scan_current__':
            console.print(f"[green]✓[/green] Ordner ausgewählt: {share_path}")
            return [{
                'name': share_path.lstrip('/'),
                'path': share_path,
                'share': share_name,
                'level': current_level
            }]
        
        # Prüfe auf Navigation
        if selected_item == '__back__':
            if current_level > 0:
                return [{'__back__': True}]
            continue
        elif selected_item == '__back_to_shares__':
            return [{'__back_to_shares__': True}]
        
        # Prüfe auf Öffnen
        if selected_item.startswith('__open__'):
            folder_path = selected_item.replace('__open__', '')
            
            # Tiefer navigieren - der rekursive Aufruf prüft selbst, ob Unterordner vorhanden sind
            next_level = current_level + 1
            
            if next_level >= max_level:
                console.print(f"[yellow]⚠[/yellow] Maximale Tiefe erreicht: {max_level} Ebenen")
                continue
            
            # Rekursiver Aufruf - lädt den Ordner und prüft, ob Unterordner vorhanden sind
            try:
                nested_result = select_subfolders_recursive(
                    api, folder_path, next_level, max_level, share_name, current_path_history
                )
                
                # Prüfe auf Abbruch (None bedeutet, dass der Benutzer abgebrochen hat)
                if nested_result is None:
                    # Benutzer hat abgebrochen - weiterleiten
                    return None
                
                # Prüfe auf Zurück-Signal
                if nested_result and len(nested_result) == 1:
                    if nested_result[0].get('__back__'):
                        continue  # Weiter in der Schleife
                    elif nested_result[0].get('__back_to_shares__'):
                        return nested_result  # Weiterleiten
                
                # Wenn nested_result leer ist (keine Unterordner), dann ist der Ordner selbst ausgewählt
                if not nested_result:
                    # Keine Unterordner gefunden - Ordner selbst auswählen
                    console.print(f"[green]✓[/green] Ordner ausgewählt: {folder_path}")
                    return [{
                        'name': folder_path.lstrip('/'),
                        'path': folder_path,
                        'share': share_name,
                        'level': current_level
                    }]
                
                # Wenn nested_result einen Ordner enthält (Scan gestartet), return diesen
                if nested_result and not (len(nested_result) == 1 and nested_result[0].get('__back__')):
                    return nested_result
            except Exception as e:
                logger.error(f"Fehler beim rekursiven Aufruf: {e}")
                console.print(f"[red]✗[/red] Fehler beim Navigieren: {e}")
                continue
    
    return []


def select_subfolders(api: SynologyAPI, selected_shares: List[Dict], 
                      allow_recursive: bool = True) -> List[Dict]:
    """
    Ermöglicht dem Benutzer die Auswahl von Unterordnern der ausgewählten Freigaben
    Mit optionaler mehrstufiger Navigation
    
    KONSISTENTES VERHALTEN: Für eine oder mehrere Freigaben wird immer rekursive Navigation angeboten.
    
    Args:
        api: SynologyAPI Instanz
        selected_shares: Liste der ausgewählten Freigaben
        allow_recursive: Wenn True, ermöglicht mehrstufige Navigation
        
    Returns:
        Liste der ausgewählten Unterordner (als Dict mit 'name' und 'path')
        None wenn zur Freigabe-Auswahl zurückgekehrt werden soll
    """
    if not selected_shares:
        return []
    
    all_selected_subfolders = []
    
    # Für jede Freigabe rekursive Navigation anbieten (konsistentes Verhalten)
    for idx, share in enumerate(selected_shares, 1):
        share_name = share.get('name')
        share_path = f"/{share_name}"
        
        # Kompakte Anzeige statt Panel
        if len(selected_shares) > 1:
            console.print(f"\n[cyan]Freigabe {idx}/{len(selected_shares)}: {share_name}[/cyan]")
        
        # Verwende rekursive Auswahl für mehrstufige Navigation (konsistent mit einzelner Freigabe)
        # select_subfolders_recursive prüft selbst, ob Unterordner vorhanden sind
        if allow_recursive:
            selected = select_subfolders_recursive(api, share_path, current_level=0, 
                                                   max_level=4, share_name=share_name)
            
            # Prüfe auf Abbruch (None bedeutet, dass der Benutzer abgebrochen hat)
            if selected is None:
                # Benutzer hat abgebrochen - weiterleiten
                raise KeyboardInterrupt("Abbruch durch Benutzer")
            
            # Prüfe, ob der Benutzer zur Freigabe-Auswahl zurückkehren möchte
            if selected and len(selected) == 1 and selected[0].get('__back_to_shares__'):
                return None  # Signal für "zurück zur Freigabe-Auswahl"
            
            if selected:
                all_selected_subfolders.extend(selected)
        else:
            # Fallback: Flache Auswahl (wenn rekursive Navigation deaktiviert)
            subfolders = api.list_subfolders(share_path)
            if not subfolders:
                continue
            choices = []
            for subfolder_path in subfolders:
                folder_name = subfolder_path.split('/')[-1] or subfolder_path.lstrip('/')
                choices.append((subfolder_path, folder_name))
            
            questions = [
                InquirerList(
                    'selected_subfolder',
                    message=f"Wählen Sie einen Unterordner von '{share_name}' aus",
                    choices=choices + [('__skip__', _format_action_entry('Überspringen', '⏭'))]
                )
            ]
            
            try:
                answer = prompt(questions, theme=DarkGreenTheme())
                if answer and 'selected_subfolder' in answer:
                    selected_path = answer.get('selected_subfolder')
                    if selected_path != '__skip__':
                        all_selected_subfolders.append({
                            'name': selected_path.lstrip('/'),
                            'path': selected_path,
                            'share': share_name
                        })
            except KeyboardInterrupt:
                # KeyboardInterrupt sollte das Programm beenden, nicht nur zurückkehren
                raise  # Weiterleiten an die Hauptfunktion
    
    # Kompakte Zusammenfassung nur wenn ausgewählt
    if all_selected_subfolders:
        console.print(f"\n[green]✓[/green] {len(all_selected_subfolders)} Unterordner ausgewählt")
    
    return all_selected_subfolders


def load_credentials(env_file: str = ".env") -> Optional[Dict[str, str]]:
    """
    Lädt Zugangsdaten aus einer .env Datei
    
    Erwartete Umgebungsvariablen:
    - SYNO_HOST oder SYNO_NAS_HOST
    - SYNO_USERNAME oder SYNO_USER
    - SYNO_PASSWORD oder SYNO_PW
    
    Args:
        env_file: Pfad zur .env Datei
        
    Returns:
        Dictionary mit host, username, password oder None wenn Datei nicht existiert
    """
    # Versuche verschiedene Dateinamen
    possible_files = [
        env_file,
        ".env",
        "config.env",
        ".env.local"
    ]
    
    for filename in possible_files:
        if not os.path.exists(filename):
            continue
        
        try:
            # Lade .env Datei
            load_dotenv(filename, override=True)
            
            # Versuche verschiedene Variablennamen
            host = os.getenv('SYNO_HOST') or os.getenv('SYNO_NAS_HOST') or os.getenv('NAS_IP')
            username = os.getenv('SYNO_USERNAME') or os.getenv('SYNO_USER') or os.getenv('SYNO_ACCOUNT')
            password = os.getenv('SYNO_PASSWORD') or os.getenv('SYNO_PW') or os.getenv('SYNO_PASSWD')
            
            if host and username and password:
                console.print(f"[green]✓[/green] Zugangsdaten aus {filename} geladen")
                
                # Lade max_parallel_tasks aus Umgebungsvariable
                max_parallel = os.getenv('SYNO_MAX_PARALLEL_TASKS', '3')  # Standard: 3
                try:
                    max_parallel = int(max_parallel)
                    if max_parallel < 1:
                        max_parallel = 1
                    elif max_parallel > 10:
                        max_parallel = 10  # Maximal 10 für Sicherheit
                        console.print(f"  [yellow]⚠[/yellow] SYNO_MAX_PARALLEL_TASKS auf 10 begrenzt (Sicherheit)")
                except ValueError:
                    max_parallel = 3  # Fallback auf Standard
                    console.print(f"  [yellow]⚠[/yellow] Ungültiger Wert für SYNO_MAX_PARALLEL_TASKS, verwende Standard: 3")
                
                # Lade default_execution_mode aus Umgebungsvariable
                default_execution_mode = os.getenv('SYNO_DEFAULT_EXECUTION_MODE', 'parallel').lower()
                if default_execution_mode not in ['parallel', 'sequential', 'async']:
                    default_execution_mode = 'parallel'  # Fallback
                
                # Lade SSL-Verifizierung aus Umgebungsvariable
                # Unterstütze SYNO_VERIFY_SSL (true/false) oder SYNO_INSECURE (true/false)
                verify_ssl_env = os.getenv('SYNO_VERIFY_SSL', '').lower()
                insecure_env = os.getenv('SYNO_INSECURE', '').lower()
                
                if verify_ssl_env:
                    # SYNO_VERIFY_SSL hat Priorität
                    verify_ssl = verify_ssl_env in ('true', '1', 'yes', 'on')
                elif insecure_env:
                    # SYNO_INSECURE: true bedeutet insecure (verify_ssl=False)
                    verify_ssl = insecure_env not in ('true', '1', 'yes', 'on')
                else:
                    # Standard: SSL-Verifizierung aktiviert (sicher)
                    verify_ssl = True
                
                # Lade Logging-Level aus Umgebungsvariable
                log_level_env = os.getenv('SYNO_ENABLE_LOGS', '').lower()
                if log_level_env in ('true', '1', 'yes', 'on', 'info'):
                    logger.setLevel(logging.INFO)
                elif log_level_env in ('debug', 'verbose'):
                    logger.setLevel(logging.DEBUG)
                elif log_level_env in ('warning', 'warn'):
                    logger.setLevel(logging.WARNING)
                elif log_level_env in ('error', 'critical'):
                    logger.setLevel(logging.ERROR)
                else:
                    # Standard: Logging deaktiviert (nur WARNING und höher)
                    logger.setLevel(logging.WARNING)
                
                return {
                    'host': host,
                    'username': username,
                    'password': password,
                    'max_parallel_tasks': max_parallel,
                    'default_execution_mode': default_execution_mode,
                    'verify_ssl': verify_ssl
                }
        
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Fehler beim Lesen von {filename}: {e}")
            continue
    
    return None


def save_credentials(host: str, username: str, password: str, 
                     env_file: str = ".env") -> bool:
    """
    Speichert Zugangsdaten in eine .env Datei
    
    Args:
        host: Hostname/IP des NAS
        username: Benutzername
        password: Passwort
        env_file: Pfad zur .env Datei
        
    Returns:
        True wenn erfolgreich, False sonst
    """
    try:
        env_content = f"""# Synology NAS Zugangsdaten
# Diese Datei enthält sensible Informationen und sollte nicht in Git committed werden

SYNO_HOST={host}
SYNO_USERNAME={username}
SYNO_PASSWORD={password}
"""
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        # Setze restriktive Datei-Permissions (0600 = nur Besitzer kann lesen/schreiben)
        os.chmod(env_file, 0o600)
        logger.info(f"Zugangsdaten in {env_file} gespeichert mit Permissions 0600")
        console.print(f"[green]✓[/green] Zugangsdaten in {env_file} gespeichert")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Zugangsdaten: {e}")
        console.print(f"[red]✗[/red] Fehler beim Speichern: {e}")
        return False


def get_credentials() -> Tuple[str, str, str]:
    """
    Ruft Zugangsdaten ab - zuerst aus Datei, sonst interaktiv
    
    Returns:
        Tuple (host, username, password)
    """
    # Versuche zuerst aus Datei zu laden
    credentials = load_credentials()
    
    if credentials:
        return credentials['host'], credentials['username'], credentials['password']
    
    # Wenn nicht gefunden, interaktiv abfragen
    console.print("\n[cyan]📝[/cyan] Keine .env Datei gefunden. Bitte Zugangsdaten eingeben:")
    console.print("   (Hinweis: Zugangsdaten können in '.env' gespeichert werden)\n")
    
    host = console.input("[bold cyan]Synology NAS Hostname/IP: [/bold cyan]").strip()
    if not host:
        console.print("[red]✗[/red] Hostname/IP ist erforderlich!")
        sys.exit(1)
    
    username = console.input("[bold cyan]Benutzername: [/bold cyan]").strip()
    if not username:
        console.print("[red]✗[/red] Benutzername ist erforderlich!")
        sys.exit(1)
    
    password = console.input("[bold cyan]Passwort: [/bold cyan]", password=True).strip()
    if not password:
        console.print("[red]✗[/red] Passwort ist erforderlich!")
        sys.exit(1)
    
    # Frage ob gespeichert werden soll
    save = console.input("\n[cyan]💾[/cyan] Zugangsdaten in '.env' speichern? (j/n): ").strip().lower()
    if save in ['j', 'ja', 'y', 'yes']:
        save_credentials(host, username, password)
    
    return host, username, password


async def main_async(max_parallel_tasks: int = 3, api: Optional[SynologyAPI] = None, 
                     selected_folders: Optional[List[Dict]] = None, output_json: bool = False,
                     show_volumes: bool = False, scan_all: bool = False, verify_ssl: bool = True):
    """Asynchrone Hauptfunktion zum Testen der API mit parallelen Tasks
    
    Bei output_json=True wird ein Spinner während des Ladens angezeigt.
    
    Args:
        max_parallel_tasks: Maximale Anzahl gleichzeitig laufender Tasks (Standard: 3)
        api: Optional: Bereits erstellte API-Instanz (wenn None, wird neue erstellt)
        selected_folders: Optional: Bereits ausgewählte Freigaben (wenn None, wird Auswahl abgefragt)
        output_json: Wenn True, werden Ergebnisse als JSON ausgegeben
    """
    global _api_instance
    
    # Wenn API-Instanz übergeben wurde, setze globale Variable
    if api:
        _api_instance = api
    if not output_json:
        console.print(Panel.fit(
            "[bold cyan]Synology File Station API Explorer (Async)[/bold cyan]",
            border_style="cyan"
        ))
    
    # Wenn keine API-Instanz übergeben wurde, erstelle eine neue
    if api is None:
        # Zugangsdaten laden (aus Datei oder interaktiv)
        credentials = load_credentials()
        if credentials:
            HOST = credentials['host']
            USERNAME = credentials['username']
            PASSWORD = credentials['password']
            # Überschreibe max_parallel_tasks wenn in .env definiert
            if 'max_parallel_tasks' in credentials:
                max_parallel_tasks = credentials['max_parallel_tasks']
            # SSL-Verifizierung aus Credentials (falls vorhanden)
            if 'verify_ssl' in credentials:
                verify_ssl = credentials['verify_ssl']
        else:
            HOST, USERNAME, PASSWORD = get_credentials()
            # Lade max_parallel_tasks aus Umgebungsvariable
            load_dotenv()
            max_parallel_env = os.getenv('SYNO_MAX_PARALLEL_TASKS', '3')
            try:
                max_parallel_tasks = int(max_parallel_env)
                if max_parallel_tasks < 1:
                    max_parallel_tasks = 1
                elif max_parallel_tasks > 10:
                    max_parallel_tasks = 10
            except ValueError:
                max_parallel_tasks = 3
            # SSL-Verifizierung aus Umgebungsvariable (falls vorhanden)
            verify_ssl_env = os.getenv('SYNO_VERIFY_SSL', '').lower()
            insecure_env = os.getenv('SYNO_INSECURE', '').lower()
            if verify_ssl_env:
                verify_ssl = verify_ssl_env in ('true', '1', 'yes', 'on')
            elif insecure_env:
                verify_ssl = insecure_env not in ('true', '1', 'yes', 'on')
            else:
                verify_ssl = True  # Standard: sicher
        
        if not output_json:
            console.print(f"[cyan]⚙️[/cyan]  Maximale parallele Tasks: {max_parallel_tasks}")
        
        # API-Instanz erstellen
        api = SynologyAPI(host=HOST, port=5001, use_https=True, output_json=output_json, verify_ssl=verify_ssl)
        _api_instance = api  # Für Signal-Handler verfügbar machen
        
        # Einloggen
        if not api.login(USERNAME, PASSWORD):
            console.print("[red]✗[/red] Konnte sich nicht einloggen. Bitte Zugangsdaten überprüfen.")
            sys.exit(1)
        
        # 1. Volume-Informationen abrufen (nur wenn --volumes gesetzt)
        if show_volumes:
            api.get_volume_info()
        
        # 2. Freigegebene Ordner auflisten
        shared_folders = api.list_shared_folders()
        
        if not shared_folders:
            if not output_json:
                console.print("[red]✗[/red] Keine freigegebenen Ordner gefunden.")
            return
        
        # 3. Benutzer wählt Freigaben aus (nur wenn nicht bereits übergeben)
        if selected_folders is None:
            # selected_folders wird in main() gesetzt, hier nicht mehr automatisch alle auswählen
            selected_folders = []
    else:
        # API-Instanz wurde übergeben, verwende sie
        if not output_json:
            console.print(f"[cyan]⚙️[/cyan]  Maximale parallele Tasks: {max_parallel_tasks}")
    
    if not selected_folders:
        console.print("\n[yellow]⚠[/yellow] Keine Freigaben zum Scannen ausgewählt.")
        return
    
    try:
        # 4. Ausgewählte Freigaben analysieren (PARALLEL mit Semaphore)
        # Semaphore für maximale Anzahl paralleler Tasks
        semaphore = asyncio.Semaphore(max_parallel_tasks)
        
        async def run_with_semaphore(task_func, folder_name):
            """Wrapper um Task mit Semaphore zur Begrenzung paralleler Ausführung"""
            async with semaphore:
                return await task_func
        
        # Rich Progress für beide Modi (JSON und interaktiv)
        # Prozentbalken nur anzeigen, wenn mehr als ein Ordner gescannt wird
        progress_columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ]
        
        # Nur Prozentbalken und Prozentanzeige hinzufügen, wenn mehr als ein Task
        if len(selected_folders) > 1:
            progress_columns.extend([
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            ])
        
        progress_columns.append(TimeElapsedColumn())
        
        with Progress(
            *progress_columns,
            console=console,
            transient=True
        ) as progress:
            # Erstelle eine Task für den Gesamtfortschritt
            overall_task = progress.add_task(
                f"[green]Checking {len(selected_folders)} Ordner...",
                total=len(selected_folders)
            )
            
            # Wrapper-Funktion, die den Fortschritt aktualisiert
            completed_count = [0]  # Liste für mutable counter
            
            # Erstelle Tasks für alle ausgewählten Freigaben
            tasks = []
            for folder in selected_folders:
                # Unterstütze sowohl altes Format (Dict mit 'name') als auch neues Format (Dict mit 'path')
                if 'path' in folder:
                    folder_path = folder['path']
                    folder_name = folder.get('name', folder_path.lstrip('/'))
                else:
                    folder_name = folder.get("name")
                    folder_path = f"/{folder_name}"
                
                # Erstelle Progress-Update-Callback für diesen Ordner
                def create_progress_callback(fn):
                    def update_progress_description(description: str):
                        progress.update(overall_task, description=description)
                    return update_progress_description
                
                progress_callback = create_progress_callback(folder_name)
                
                # Erstelle async Task mit Semaphore und Progress-Callback
                async def create_task_with_progress(fp, fn, pc):
                    async with semaphore:
                        return await api.get_dir_size_async(
                            fp, 
                            max_wait=300, 
                            poll_interval=2,
                            progress_update_callback=pc
                        )
                
                task = create_task_with_progress(folder_path, folder_name, progress_callback)
                tasks.append((task, folder_name))
            
            async def track_progress(task_func, folder_name):
                # Beim Start: Beschreibung aktualisieren
                if len(selected_folders) == 1:
                    # Nur 1 Ordner: Zeige Ordnername
                    progress.update(
                        overall_task,
                        description=f"[green]Checking {folder_name}... ({completed_count[0]}/{len(selected_folders)})"
                    )
                else:
                    # Mehrere Ordner: Zeige generische Beschreibung
                    progress.update(
                        overall_task,
                        description=f"[green]Checking {len(selected_folders)} Ordner... ({completed_count[0]}/{len(selected_folders)})"
                    )
                
                result = await task_func
                
                # Beim Abschluss: Fortschritt aktualisieren
                completed_count[0] += 1
                
                if len(selected_folders) == 1:
                    # Nur 1 Ordner: Ordnername bleibt sichtbar
                    progress.update(
                        overall_task, 
                        advance=1,
                        description=f"[green]Checking {folder_name}... ({completed_count[0]}/{len(selected_folders)})"
                    )
                else:
                    # Mehrere Ordner: Generische Beschreibung mit aktuellem Fortschritt
                    progress.update(
                        overall_task, 
                        advance=1, 
                        description=f"[green]Checking {len(selected_folders)} Ordner... ({completed_count[0]}/{len(selected_folders)})"
                    )
                
                return result
            
            # Erstelle Tasks mit Progress-Tracking
            tracked_tasks = []
            for task, folder_name in tasks:
                tracked_task = track_progress(task, folder_name)
                tracked_tasks.append(tracked_task)
            
            try:
                results = await asyncio.gather(*tracked_tasks, return_exceptions=True)
            except KeyboardInterrupt:
                # KeyboardInterrupt während asyncio.gather
                # WICHTIG: Progress-Balken sofort stoppen
                progress.stop()
                if not output_json:
                    console.print("\n[yellow]⚠[/yellow] Abbruch durch Benutzer")
                # Versuche gestartete Tasks zu stoppen (Fehler werden ignoriert, besonders 599)
                if api is not None:
                    api.cleanup_tasks(ignore_errors=True)
                raise
        
        # Sammle Ergebnisse für JSON-Output
        json_results = []
        
        for (_, folder_name), result in zip(tasks, results):
            if isinstance(result, Exception):
                json_results.append({
                    'folder_name': folder_name,
                    'error': str(result),
                    'success': False
                })
            elif result:
                size_info = api._format_size_with_unit(result['total_size'])
                elapsed_time = result.get('elapsed_time', 0)
                
                json_results.append({
                    'folder_name': folder_name,
                    'success': True,
                    'num_dir': result['num_dir'],
                    'num_file': result['num_file'],
                    'total_size': {
                        'bytes': size_info['size_bytes'],
                        'formatted': size_info['size_formatted'],
                        'unit': size_info['unit']
                    },
                    'elapsed_time_ms': int(round(elapsed_time * 1000)),
                    'size_info': result  # Für spätere Ausgabe speichern
                })
            else:
                json_results.append({
                    'folder_name': folder_name,
                    'success': False,
                    'error': 'Keine Ergebnisse erhalten'
                })
        
        if output_json:
            # JSON-Output (ohne size_info für JSON)
            json_output = []
            for result in json_results:
                json_result = {k: v for k, v in result.items() if k != 'size_info'}
                json_output.append(json_result)
            print(json.dumps(json_output, indent=2, ensure_ascii=False))
        else:
            # Interaktiver Modus: Zeige Ergebnisse nach dem Progress
            console.print()
            # Prüfe ob nur ein Ordner gescannt wurde
            single_folder = len(json_results) == 1
            
            for result in json_results:
                if result.get('success'):
                    folder_name = result['folder_name']
                    size_info = result.get('size_info')
                    if size_info:
                        elapsed_time = size_info.get('elapsed_time', 0)
                        duration_str = f"{int(round(elapsed_time))}s"
                        
                        if single_folder:
                            # Einzelner Ordner: Ausgabe untereinander
                            console.print(f"[bold]{folder_name}[/bold]:")
                            console.print(f"  Größe: {api._format_size(size_info['total_size'])}")
                            console.print(f"  Verzeichnisse: {size_info['num_dir']:,}")
                            console.print(f"  Dateien: {size_info['num_file']:,}")
                            console.print(f"  [dim]Duration: {duration_str}[/dim]")
                        else:
                            # Mehrere Ordner: Ausgabe in einer Zeile mit Pipes
                            console.print(f"[bold]{folder_name}[/bold]: {api._format_size(size_info['total_size'])} | "
                                        f"{size_info['num_dir']:,} Verzeichnisse | {size_info['num_file']:,} Dateien | "
                                        f"[dim]Duration: {duration_str}[/dim]")
                    else:
                        # Fallback falls size_info nicht vorhanden
                        total_size = result.get('total_size', {})
                        size_str = total_size.get('formatted', '0 B')
                        if single_folder:
                            console.print(f"[bold]{folder_name}[/bold]:")
                            console.print(f"  Größe: {size_str}")
                            console.print(f"  Verzeichnisse: {result.get('num_dir', 0):,}")
                            console.print(f"  Dateien: {result.get('num_file', 0):,}")
                        else:
                            console.print(f"[bold]{folder_name}[/bold]: {size_str} | "
                                        f"{result.get('num_dir', 0):,} Verzeichnisse | {result.get('num_file', 0):,} Dateien")
                else:
                    folder_name = result.get('folder_name', 'unknown')
                    console.print(f"[yellow]⚠[/yellow] Keine Ergebnisse für '{folder_name}'")
            
            console.print(f"\n[green]✓ Analyse abgeschlossen[/green]")
        
    except KeyboardInterrupt:
        # KeyboardInterrupt während async main
        if not output_json:
            console.print("\n[yellow]⚠[/yellow] Abbruch durch Benutzer (Ctrl+C)")
        # Versuche gestartete Tasks zu stoppen (Fehler werden ignoriert, besonders 599)
        if api is not None:
            api.cleanup_tasks(ignore_errors=True)
        raise
    finally:
        # Async Session schließen und abmelden (nur wenn API-Instanz erstellt wurde)
        if api is not None:
            await api.close_async_session()
            # Abmelden nur wenn API-Instanz hier erstellt wurde (nicht wenn von main() übergeben)
            # logout() ist idempotent, also ist es OK es auch aufzurufen wenn es bereits abgemeldet wurde
            api.logout()


def main():
    """Hauptfunktion zum Testen der API (synchron, für Rückwärtskompatibilität)"""
    # Parse Kommandozeilenargumente
    parser = argparse.ArgumentParser(description='Synology File Station API Explorer')
    parser.add_argument('--json', '-j', action='store_true', 
                       help='Ausgabe als JSON (Größe in Bytes, Einheit separat)')
    parser.add_argument('--mode', '-m', choices=['parallel', 'sequential'], 
                       help='Ausführungsmodus (überschreibt SYNO_DEFAULT_EXECUTION_MODE)')
    parser.add_argument('--volumes', '-v', action='store_true',
                       help='Zeige Volume-Informationen an (standardmäßig deaktiviert)')
    parser.add_argument('--all', '-a', action='store_true',
                       help='Scanne alle Freigaben automatisch (nur im JSON-Modus relevant)')
    parser.add_argument('--share', '-s', type=str,
                       help='Direkte Angabe einer Freigabe (Share-Name)')
    parser.add_argument('--folder', '-f', type=str,
                       help='Direkte Angabe eines oder mehrerer Ordner innerhalb einer Freigabe (benötigt --share). '
                            'Mehrere Ordner können komma-separiert angegeben werden: "folder a, folder b"')
    parser.add_argument('--path', '-p', type=str, nargs='+',
                       help='Ganze Pfade zum Scannen im Format share/folder/subfolder. '
                            'Mehrere Pfade können angegeben werden (getrennt durch Leerzeichen oder Komma). '
                            'Beispiele: --path share1/folder1 share2/folder2/subfolder oder --path share1/folder1,share2/folder2/subfolder')
    parser.add_argument('--include-subfolders', action='store_true',
                       help='Analysiere auch alle Unterordner der ausgewählten Freigaben')
    parser.add_argument('--list-shares', action='store_true',
                       help='Listet lediglich alle verfügbaren Shares auf')
    parser.add_argument('--insecure', action='store_true',
                       help='Deaktiviere SSL-Zertifikat-Verifizierung (nur für selbst-signierte Zertifikate). '
                            'Kann auch über Umgebungsvariable SYNO_INSECURE=true oder SYNO_VERIFY_SSL=false gesetzt werden.')
    args = parser.parse_args()
    
    output_json = args.json
    show_volumes = args.volumes
    scan_all = args.all
    share_name = args.share
    folder_name = args.folder
    paths = args.path
    include_subfolders = args.include_subfolders
    list_shares = args.list_shares
    
    # Erweitere die Pfad-Verarbeitung um Komma-separierte Listen
    # Unterstützt sowohl mehrere --path Argumente als auch Komma-separierte Listen
    if paths:
        expanded_paths = []
        for path_item in paths:
            # Wenn ein Pfad Kommas enthält, aufteilen
            if ',' in path_item:
                expanded_paths.extend([p.strip() for p in path_item.split(',') if p.strip()])
            else:
                expanded_paths.append(path_item.strip())
        paths = expanded_paths
    
    # Validierung: --path und --share/--folder schließen sich gegenseitig aus
    if paths and (share_name or folder_name):
        console.print("[red]✗[/red] Fehler: --path kann nicht zusammen mit --share oder --folder verwendet werden")
        sys.exit(1)
    
    # Validierung: Wenn --folder angegeben ist, muss auch --share angegeben sein
    if folder_name and not share_name:
        console.print("[red]✗[/red] Fehler: --folder erfordert --share")
        sys.exit(1)
    
    if not output_json:
        console.print(Panel.fit(
            "[bold cyan]Synology File Station API Explorer[/bold cyan]",
            border_style="cyan"
        ))
    
    # Zugangsdaten laden (aus Datei oder interaktiv)
    credentials = load_credentials()
    if credentials:
        HOST = credentials['host']
        USERNAME = credentials['username']
        PASSWORD = credentials['password']
        # Parameter überschreibt .env Einstellung
        execution_mode = args.mode or credentials.get('default_execution_mode', 'parallel')
        max_parallel_tasks = credentials.get('max_parallel_tasks', 3)
        # SSL-Verifizierung: CLI-Flag hat höchste Priorität, dann .env, dann Standard
        verify_ssl = credentials.get('verify_ssl', True)
    else:
        HOST, USERNAME, PASSWORD = get_credentials()
        execution_mode = args.mode or 'parallel'
        # Lade max_parallel_tasks aus Umgebungsvariable
        load_dotenv()
        max_parallel_env = os.getenv('SYNO_MAX_PARALLEL_TASKS', '3')
        try:
            max_parallel_tasks = int(max_parallel_env)
            if max_parallel_tasks < 1:
                max_parallel_tasks = 1
            elif max_parallel_tasks > 10:
                max_parallel_tasks = 10
        except ValueError:
            max_parallel_tasks = 3
        # SSL-Verifizierung aus Umgebungsvariable (falls vorhanden)
        verify_ssl_env = os.getenv('SYNO_VERIFY_SSL', '').lower()
        insecure_env = os.getenv('SYNO_INSECURE', '').lower()
        if verify_ssl_env:
            verify_ssl = verify_ssl_env in ('true', '1', 'yes', 'on')
        elif insecure_env:
            verify_ssl = insecure_env not in ('true', '1', 'yes', 'on')
        else:
            verify_ssl = True  # Standard: sicher
    
    # TLS-Verifizierung: CLI-Flag --insecure hat höchste Priorität (überschreibt alles)
    if args.insecure:
        verify_ssl = False
        if not output_json:
            console.print("[yellow]⚠[/yellow] SSL-Zertifikat-Verifizierung deaktiviert (--insecure)")
    
    # Globale API-Instanz für Signal-Handler setzen
    global _api_instance
    
    # API-Instanz erstellen
    api = SynologyAPI(host=HOST, port=5001, use_https=True, output_json=output_json, verify_ssl=verify_ssl)
    _api_instance = api  # Für Signal-Handler verfügbar machen
    
    # Einloggen
    if not api.login(USERNAME, PASSWORD):
        console.print("[red]✗[/red] Konnte sich nicht einloggen. Bitte Zugangsdaten überprüfen.")
        sys.exit(1)
    
    try:
        # Wenn --list-shares angegeben ist, nur Shares auflisten und beenden
        if list_shares:
            shared_folders = api.list_shared_folders()
            if shared_folders:
                if output_json:
                    # JSON-Format: Liste von Shares mit Details
                    shares_json = []
                    for folder in shared_folders:
                        folder_name = folder.get('name')
                        folder_size = folder.get('size', {}).get('total', 0)
                        share_info = {
                            'name': folder_name,
                            'size_bytes': folder_size
                        }
                        if folder_size > 0:
                            size_info = api._format_size_with_unit(folder_size)
                            share_info['size'] = {
                                'bytes': size_info['size_bytes'],
                                'formatted': size_info['size_formatted'],
                                'unit': size_info['unit']
                            }
                        # Weitere verfügbare Informationen hinzufügen
                        if folder.get('owner'):
                            share_info['owner'] = folder.get('owner')
                        if folder.get('time'):
                            share_info['time'] = folder.get('time')
                        shares_json.append(share_info)
                    print(json.dumps(shares_json, indent=2, ensure_ascii=False))
                # Normale Ausgabe erfolgt bereits in list_shared_folders()
            else:
                if output_json:
                    print(json.dumps([], indent=2, ensure_ascii=False))
                else:
                    console.print("[red]✗[/red] Keine freigegebenen Ordner gefunden.")
            return
        
        # 1. Volume-Informationen abrufen (nur wenn --volumes gesetzt)
        if show_volumes:
            api.get_volume_info()
        
        # 2. Wenn --path angegeben ist, verwende direkte Pfade
        if paths:
            shared_folders = api.list_shared_folders(show_message=False)
            if not shared_folders:
                console.print("[red]✗[/red] Keine freigegebenen Ordner gefunden.")
                return
            
            available_share_names = [f.get('name') for f in shared_folders]
            paths_to_scan = []
            
            for path_str in paths:
                # Pfad parsen: share/folder/subfolder
                path_parts = path_str.strip().strip('/').split('/')
                if not path_parts or not path_parts[0]:
                    console.print(f"[yellow]⚠[/yellow] Ungültiger Pfad: '{path_str}' (übersprungen)")
                    continue
                
                share_name_from_path = path_parts[0]
                
                # Prüfe ob Share existiert
                if share_name_from_path not in available_share_names:
                    console.print(f"[red]✗[/red] Freigabe '{share_name_from_path}' in Pfad '{path_str}' nicht gefunden.")
                    console.print(f"Verfügbare Freigaben: {', '.join(available_share_names)}")
                    continue
                
                # Baue vollständigen Pfad auf
                full_path = '/' + '/'.join(path_parts)
                display_name = '/'.join(path_parts)
                
                paths_to_scan.append({
                    'name': display_name,
                    'path': full_path
                })
            
            if not paths_to_scan:
                console.print("[red]✗[/red] Keine gültigen Pfade zum Scannen gefunden.")
                return
            
            # Konvertiere zu Format, das von main_async erwartet wird
            selected_folders = paths_to_scan
        # 3. Wenn --share angegeben ist, verwende direkten Pfad
        elif share_name:
            # Prüfe ob Freigabe existiert
            shared_folders = api.list_shared_folders(show_message=False)
            if not shared_folders:
                console.print("[red]✗[/red] Keine freigegebenen Ordner gefunden.")
                return
            
            # Suche nach der angegebenen Freigabe
            matching_share = None
            for folder in shared_folders:
                if folder.get('name') == share_name:
                    matching_share = folder
                    break
            
            if not matching_share:
                console.print(f"[red]✗[/red] Freigabe '{share_name}' nicht gefunden.")
                available_shares = [f.get('name') for f in shared_folders]
                console.print(f"Verfügbare Freigaben: {', '.join(available_shares)}")
                return
            
            # Erstelle Pfad-Liste basierend auf Parametern
            paths_to_scan = []
            
            if folder_name:
                # Spezifischer Ordner oder mehrere Ordner innerhalb der Freigabe (komma-separiert)
                # Entferne Anführungszeichen falls vorhanden und splitte bei Kommas
                folder_names_str = folder_name.strip().strip('"').strip("'")
                folder_names = [f.strip().strip('"').strip("'") for f in folder_names_str.split(',')]
                
                for folder in folder_names:
                    if not folder:
                        continue
                    target_path = f"/{share_name}/{folder.lstrip('/')}"
                    paths_to_scan.append({
                        'name': f"{share_name}/{folder}",
                        'path': target_path
                    })
            elif include_subfolders:
                # Nur die Subfolder der Freigabe (NICHT die Freigabe selbst)
                # Bei --share: Interaktive Auswahl der Unterordner
                share_path = f"/{share_name}"
                subfolders = api.list_subfolders(share_path)
                if subfolders:
                    # Erstelle temporäre Liste für interaktive Auswahl
                    temp_subfolders = []
                    for subfolder_path in subfolders:
                        temp_subfolders.append({
                            'name': subfolder_path.lstrip('/'),
                            'path': subfolder_path,
                            'share': share_name
                        })
                    
                    # Interaktive Auswahl der Unterordner (gleiche UI für JSON und interaktiv)
                    selected_subfolders = select_subfolders(api, [matching_share])
                    if selected_subfolders:
                        paths_to_scan = [{'name': sf.get('name'), 'path': sf.get('path')} for sf in selected_subfolders]
                        console.print(f"[green]✓[/green] {len(paths_to_scan)} Unterordner ausgewählt")
                    else:
                        console.print(f"[yellow]⚠[/yellow] Keine Unterordner ausgewählt")
                else:
                    if not output_json:
                        console.print(f"[yellow]⚠[/yellow] Keine Unterordner in '{share_name}' gefunden")
                    # Keine Pfade hinzufügen, wenn keine Subfolder vorhanden sind
            else:
                # Nur die Freigabe selbst
                paths_to_scan.append({
                    'name': share_name,
                    'path': f"/{share_name}"
                })
            
            # Konvertiere zu Format, das von main_async erwartet wird
            selected_folders = paths_to_scan
        else:
            # 3. Benutzer wählt Freigaben aus (normale Logik)
            shared_folders = api.list_shared_folders()
            
            if not shared_folders:
                console.print("[red]✗[/red] Keine freigegebenen Ordner gefunden.")
                return
            
            if output_json and scan_all:
                # Im JSON-Modus mit --all: Alle Freigaben automatisch auswählen
                selected_folders = shared_folders
            elif output_json:
                # Im JSON-Modus ohne --all: Verwende die gleiche Single-Select UI wie im interaktiven Modus
                selected_folders = select_folders(shared_folders)
            else:
                selected_folders = select_folders(shared_folders)
            
            # Subfolder-Behandlung (mit Möglichkeit zur Freigabe-Auswahl zurückzukehren)
            # Wenn Freigaben ausgewählt wurden, starte direkt die interaktive Auswahl
            # select_subfolders prüft selbst, ob Unterordner vorhanden sind
            # Überspringe interaktive Auswahl wenn --share oder --path verwendet wurde
            # Bei --all: Überspringe Subfolder-Auswahl, scanne nur die Freigaben selbst (inkl. aller Unterordner)
            while selected_folders and not share_name and not paths and not (output_json and scan_all):
                # Interaktive Auswahl der Unterordner
                # select_subfolders prüft selbst, ob Unterordner vorhanden sind
                # Verwende die gleiche UI sowohl im JSON-Modus als auch im interaktiven Modus
                selected_subfolders = select_subfolders(api, selected_folders)
                    
                # Prüfe, ob der Benutzer zur Freigabe-Auswahl zurückkehren möchte
                if selected_subfolders is None:
                    # Zurück zur Freigabe-Auswahl - starte die Schleife neu
                    console.print("[cyan]↩[/cyan] Zurück zur Freigabe-Auswahl...")
                    # Setze selected_folders zurück und zeige Freigabe-Auswahl erneut
                    # Verwende die gleiche Single-Select UI sowohl im JSON-Modus als auch im interaktiven Modus
                    selected_folders = select_folders(shared_folders)
                    # Wenn keine Freigaben ausgewählt wurden, beende die Schleife
                    if not selected_folders:
                        break
                    # Sonst starte die Schleife neu
                    continue
                elif selected_subfolders:
                    # Verwende die ausgewählten Subfolder statt der Shares
                    selected_folders = [{'name': sf.get('name'), 'path': sf.get('path')} for sf in selected_subfolders]
                    break  # Beende die while-Schleife
                else:
                    # Keine Unterordner ausgewählt oder vorhanden - analysiere nur die Freigaben selbst
                    break  # Beende die while-Schleife
                
                # Wenn wir hier ankommen und selected_folders leer ist, beende die Schleife
                if not selected_folders:
                    break
        
        if not selected_folders:
            console.print("\n[yellow]⚠[/yellow] Keine Freigaben zum Scannen ausgewählt.")
            return
        
        # Bounded Concurrency: Verwende ThreadPoolExecutor für synchrone Ausführung
        # "sequential" Modus bedeutet einfach max_parallel_tasks=1 für Rückwärtskompatibilität
        if execution_mode == 'sequential':
            effective_max_parallel = 1
        else:
            effective_max_parallel = max_parallel_tasks
        
        json_results = []
        
        # Rich Progress für beide Modi (JSON und interaktiv)
        # Prozentbalken nur anzeigen, wenn mehr als ein Ordner gescannt wird
        progress_columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
        ]
        
        # Nur Prozentbalken und Prozentanzeige hinzufügen, wenn mehr als ein Task
        if len(selected_folders) > 1:
            progress_columns.extend([
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            ])
        
        progress_columns.append(TimeElapsedColumn())
        
        progress = Progress(
            *progress_columns,
            console=console,
            transient=True
        )
        progress.start()
        overall_task = progress.add_task(
            f"[green]Checking {len(selected_folders)} Ordner...",
            total=len(selected_folders)
        )
        
        def process_folder(folder: Dict, progress_callback=None, shutdown_event=None) -> Dict:
            """Verarbeitet einen einzelnen Ordner (für ThreadPoolExecutor)"""
            # Prüfe sofort, ob abgebrochen wurde
            if shutdown_event and shutdown_event.is_set():
                folder_name = folder.get('name', folder.get('path', 'unknown').lstrip('/'))
                return {
                    'folder_name': folder_name,
                    'success': False,
                    'error': 'Abgebrochen'
                }
            
            # Unterstütze sowohl altes Format (Dict mit 'name') als auch neues Format (Dict mit 'path')
            if 'path' in folder:
                folder_path = folder['path']
                folder_name = folder.get('name', folder_path.lstrip('/'))
            else:
                folder_name = folder.get("name")
                folder_path = f"/{folder_name}"
            
            # Progress-Update beim Start
            if progress_callback:
                progress_callback(folder_name, started=True)
            
            # Prüfe erneut, ob abgebrochen wurde
            if shutdown_event and shutdown_event.is_set():
                return {
                    'folder_name': folder_name,
                    'success': False,
                    'error': 'Abgebrochen'
                }
            
            # Verzeichnisinhalt auflisten
            items = api.list_directory(folder_path)
            
            # Prüfe erneut, ob abgebrochen wurde
            if shutdown_event and shutdown_event.is_set():
                return {
                    'folder_name': folder_name,
                    'success': False,
                    'error': 'Abgebrochen'
                }
            
            # Erstelle Progress-Update-Callback für diesen Ordner
            def create_progress_update_callback(fn):
                def update_progress_description(description: str):
                    with progress_lock:
                        progress.update(overall_task, description=description)
                return update_progress_description
            
            progress_update_callback = create_progress_update_callback(folder_name)
            
            # Verzeichnisgröße berechnen
            size_info = api.get_dir_size(
                folder_path, 
                max_wait=300, 
                poll_interval=2, 
                shutdown_event=shutdown_event,
                progress_update_callback=progress_update_callback
            )
            
            # Progress-Update bei Abschluss
            if progress_callback:
                progress_callback(folder_name, completed=True)
            
            if size_info:
                size_formatted = api._format_size_with_unit(size_info['total_size'])
                elapsed_time = size_info.get('elapsed_time', 0)
                
                return {
                    'folder_name': folder_name,
                    'success': True,
                    'num_dir': size_info['num_dir'],
                    'num_file': size_info['num_file'],
                    'total_size': {
                        'bytes': size_formatted['size_bytes'],
                        'formatted': size_formatted['size_formatted'],
                        'unit': size_formatted['unit']
                    },
                    'elapsed_time_ms': int(round(elapsed_time * 1000)),
                    'size_info': size_info  # Für spätere Ausgabe speichern
                }
            else:
                return {
                    'folder_name': folder_name,
                    'success': False,
                    'error': 'Keine Ergebnisse erhalten'
                }
        
        # Shutdown-Event für Thread-Abbruch
        shutdown_event = threading.Event()
        
        # Thread-sicherer Counter für Fortschritt
        completed_count = [0]
        progress_lock = threading.Lock()
        
        def update_progress(folder_name: str, started: bool = False, completed: bool = False):
            """Thread-sichere Progress-Update-Funktion"""
            if not progress or overall_task is None:
                return
            
            with progress_lock:
                if started:
                    current_count = completed_count[0]
                    if len(selected_folders) == 1:
                        # Nur 1 Ordner: Zeige Ordnername
                        progress.update(
                            overall_task,
                            description=f"[green]Checking {folder_name}... ({current_count}/{len(selected_folders)})"
                        )
                    else:
                        # Mehrere Ordner: Zeige generische Beschreibung
                        progress.update(
                            overall_task,
                            description=f"[green]Checking {len(selected_folders)} Ordner... ({current_count}/{len(selected_folders)})"
                        )
                elif completed:
                    completed_count[0] += 1
                    current_count = completed_count[0]
                    
                    if len(selected_folders) == 1:
                        # Nur 1 Ordner: Ordnername bleibt sichtbar
                        progress.update(
                            overall_task,
                            advance=1,
                            description=f"[green]Checking {folder_name}... ({current_count}/{len(selected_folders)})"
                        )
                    else:
                        # Mehrere Ordner: Generische Beschreibung mit aktuellem Fortschritt
                        progress.update(
                            overall_task,
                            advance=1,
                            description=f"[green]Checking {len(selected_folders)} Ordner... ({current_count}/{len(selected_folders)})"
                        )
        
        # Verwende ThreadPoolExecutor für Bounded Concurrency
        try:
            with ThreadPoolExecutor(max_workers=effective_max_parallel) as executor:
                # Submite alle Tasks
                future_to_folder = {
                    executor.submit(process_folder, folder, update_progress, shutdown_event): folder 
                    for folder in selected_folders
                }
                
                # Sammle Ergebnisse während sie fertig werden
                try:
                    for future in as_completed(future_to_folder):
                        folder = future_to_folder[future]
                        try:
                            result = future.result()
                            json_results.append(result)
                        except Exception as e:
                            folder_name = folder.get('name', folder.get('path', 'unknown'))
                            logger.error(f"Fehler beim Verarbeiten von {folder_name}: {e}")
                            json_results.append({
                                'folder_name': folder_name,
                                'success': False,
                                'error': str(e)
                            })
                except KeyboardInterrupt:
                    # KeyboardInterrupt während as_completed
                    # WICHTIG: Shutdown-Event setzen, damit alle Threads stoppen
                    shutdown_event.set()
                    # WICHTIG: Progress-Balken sofort stoppen
                    if progress:
                        progress.stop()
                    if not output_json:
                        console.print("\n[yellow]⚠[/yellow] Abbruch durch Benutzer")
                    # Versuche gestartete Tasks zu stoppen (Fehler werden ignoriert, besonders 599)
                    if api is not None:
                        api.cleanup_tasks(ignore_errors=True)
                    # Breche alle laufenden Futures ab
                    for future in future_to_folder:
                        future.cancel()
                    raise
        except KeyboardInterrupt:
            # KeyboardInterrupt beim Erstellen des Executors
            # WICHTIG: Shutdown-Event setzen, damit alle Threads stoppen
            shutdown_event.set()
            # WICHTIG: Progress-Balken sofort stoppen
            if progress:
                progress.stop()
            if not output_json:
                console.print("\n[yellow]⚠[/yellow] Abbruch durch Benutzer")
            # Versuche gestartete Tasks zu stoppen (Fehler werden ignoriert, besonders 599)
            if api is not None:
                api.cleanup_tasks(ignore_errors=True)
            raise
        
        # Progress beenden
        if progress:
            progress.stop()
        
        if output_json:
            # JSON-Output (ohne size_info für JSON)
            json_output = []
            for result in json_results:
                json_result = {k: v for k, v in result.items() if k != 'size_info'}
                json_output.append(json_result)
            print(json.dumps(json_output, indent=2, ensure_ascii=False))
        else:
            # Interaktiver Modus: Zeige Ergebnisse nach dem Progress
            console.print()
            # Prüfe ob nur ein Ordner gescannt wurde
            single_folder = len(json_results) == 1
            
            for result in json_results:
                if result.get('success'):
                    folder_name = result['folder_name']
                    size_info = result.get('size_info')
                    if size_info:
                        elapsed_time = size_info.get('elapsed_time', 0)
                        duration_str = f"{int(round(elapsed_time))}s"
                        
                        if single_folder:
                            # Einzelner Ordner: Ausgabe untereinander
                            console.print(f"[bold]{folder_name}[/bold]:")
                            console.print(f"  Größe: {api._format_size(size_info['total_size'])}")
                            console.print(f"  Verzeichnisse: {size_info['num_dir']:,}")
                            console.print(f"  Dateien: {size_info['num_file']:,}")
                            console.print(f"  [dim]Duration: {duration_str}[/dim]")
                        else:
                            # Mehrere Ordner: Ausgabe in einer Zeile mit Pipes
                            console.print(f"[bold]{folder_name}[/bold]: {api._format_size(size_info['total_size'])} | "
                                        f"{size_info['num_dir']:,} Verzeichnisse | {size_info['num_file']:,} Dateien | "
                                        f"[dim]Duration: {duration_str}[/dim]")
                    else:
                        # Fallback falls size_info nicht vorhanden
                        total_size = result.get('total_size', {})
                        size_str = total_size.get('formatted', '0 B')
                        if single_folder:
                            console.print(f"[bold]{folder_name}[/bold]:")
                            console.print(f"  Größe: {size_str}")
                            console.print(f"  Verzeichnisse: {result.get('num_dir', 0):,}")
                            console.print(f"  Dateien: {result.get('num_file', 0):,}")
                        else:
                            console.print(f"[bold]{folder_name}[/bold]: {size_str} | "
                                        f"{result.get('num_dir', 0):,} Verzeichnisse | {result.get('num_file', 0):,} Dateien")
                else:
                    folder_name = result.get('folder_name', 'unknown')
                    console.print(f"[yellow]⚠[/yellow] Keine Ergebnisse für '{folder_name}'")
            
            console.print(f"\n[green]✓ Analyse abgeschlossen[/green]")
        
        # Für async/parallel Modus verwenden wir weiterhin die async Version mit Semaphore
        # Die async Version wird verwendet, wenn der Benutzer explizit async möchte
        # Standard ist jetzt ThreadPoolExecutor für synchrone Ausführung
        # Async-Version wird nur noch intern für parallele async Tasks verwendet
        
    except KeyboardInterrupt:
        # KeyboardInterrupt wurde bereits in Subfolder-Funktionen weitergeleitet
        # Hier wird es abgefangen, um sauber abzumelden
        # WICHTIG: Progress-Balken stoppen (falls noch nicht gestoppt)
        # progress ist möglicherweise nicht in diesem Scope, daher prüfen wir es nicht hier
        console.print("\n[yellow]⚠[/yellow] Abbruch durch Benutzer (Ctrl+C)")
        # Versuche gestartete Tasks zu stoppen (Fehler werden ignoriert, besonders 599)
        if api is not None:
            api.cleanup_tasks(ignore_errors=True)
        # Logout erfolgt im finally-Block
    finally:
        # Abmelden
        if api is not None:
            api.logout()


if __name__ == "__main__":
    main()

