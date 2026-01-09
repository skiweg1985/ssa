#!/usr/bin/env python3
"""
Unit-Tests für die get_dir_size() Polling-Logik mit gemockten API-Calls
Testet die komplette Polling-Schleife ohne echte API-Verbindungen.
"""

import sys
import os
import time
import pytest
from unittest.mock import Mock, patch
from typing import Dict, Optional
import threading

# Füge das aktuelle Verzeichnis zum Python-Pfad hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importiere die SynologyAPI-Klasse
from explore_syno_api import SynologyAPI


@pytest.fixture
def api_instance():
    """Erstellt eine SynologyAPI-Instanz für Tests"""
    api = SynologyAPI.__new__(SynologyAPI)
    api.output_json = True  # Unterdrücke Print-Ausgaben für Tests
    api._active_tasks = []
    api.sid = "test_session_id"  # Mock Session-ID
    api._last_api_call_time = 0
    api.rate_limit_delay = 0.1  # Kurze Delay für Tests
    return api


class TestGetDirSizePolling:
    """Test-Klasse für get_dir_size() Polling-Logik"""
    
    @patch('explore_syno_api.time.sleep')
    def test_task_finished_immediately(self, mock_sleep, api_instance, mocker):
        """Test: Task wird sofort nach Start fertig (initialer Check)"""
        print("\n  Teste: Task wird sofort fertig (initialer Check)")
        
        task_id = "test_task_123"
        
        # Mock API-Calls
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=[
            # Task start
            {
                "success": True,
                "data": {"taskid": task_id}
            },
            # Initial status check - Task ist bereits fertig
            {
                "success": True,
                "data": {
                    "finished": True,
                    "num_dir": 5,
                    "num_file": 10,
                    "total_size": 50000
                }
            }
        ])
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        print(f"    Ergebnis: {result}")
        assert result is not None, "Sollte Ergebnis zurückgeben"
        assert result['num_dir'] == 5
        assert result['num_file'] == 10
        assert result['total_size'] == 50000
        assert 'elapsed_time' in result
        assert task_id not in api_instance._active_tasks, "Task sollte aus _active_tasks entfernt werden"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_finished_after_polling(self, mock_sleep, api_instance, mocker):
        """Test: Task wird nach mehreren Polling-Zyklen fertig"""
        print("\n  Teste: Task wird nach Polling fertig")
        
        task_id = "test_task_456"
        call_count = [0]  # Mutable counter für Side-Effekt
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Task start
                return {
                    "success": True,
                    "data": {"taskid": task_id}
                }
            elif call_count[0] == 2:
                # Initial status - noch nicht fertig
                return {
                    "success": True,
                    "data": {
                        "finished": False,
                        "progress": 0.3,
                        "processed_num": 10,
                        "total": 30
                    }
                }
            elif call_count[0] == 3:
                # Erster Polling-Check - noch nicht fertig
                return {
                    "success": True,
                    "data": {
                        "finished": False,
                        "progress": 0.6,
                        "processed_num": 18,
                        "total": 30
                    }
                }
            elif call_count[0] == 4:
                # Zweiter Polling-Check - jetzt fertig!
                return {
                    "success": True,
                    "data": {
                        "finished": True,
                        "num_dir": 3,
                        "num_file": 7,
                        "total_size": 30000
                    }
                }
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        print(f"    Ergebnis: {result}")
        print(f"    API-Calls: {call_count[0]}")
        assert result is not None, "Sollte Ergebnis zurückgeben"
        assert result['num_dir'] == 3
        assert result['num_file'] == 7
        assert result['total_size'] == 30000
        assert call_count[0] >= 4, "Sollte mindestens 4 API-Calls gemacht haben (start + initial + 2 polls)"
        assert task_id not in api_instance._active_tasks
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_finished_with_string_true(self, mock_sleep, api_instance, mocker):
        """Test: Task wird fertig mit finished='true' (String)"""
        print("\n  Teste: Task wird fertig mit finished='true' (String)")
        
        task_id = "test_task_789"
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                return {
                    "success": True,
                    "data": {
                        "finished": "true",  # String statt Boolean
                        "num_dir": 2,
                        "num_file": 4,
                        "total_size": 20000
                    }
                }
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        assert result is not None, "Sollte Ergebnis zurückgeben auch bei String 'true'"
        assert result['num_dir'] == 2
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_finished_with_integer_one(self, mock_sleep, api_instance, mocker):
        """Test: Task wird fertig mit finished=1 (Integer)"""
        print("\n  Teste: Task wird fertig mit finished=1 (Integer)")
        
        task_id = "test_task_int"
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                return {
                    "success": True,
                    "data": {
                        "finished": 1,  # Integer statt Boolean
                        "num_dir": 1,
                        "num_file": 2,
                        "total_size": 10000
                    }
                }
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        assert result is not None, "Sollte Ergebnis zurückgeben auch bei Integer 1"
        assert result['num_dir'] == 1
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_timeout(self, mock_sleep, api_instance, mocker):
        """Test: Task erreicht Timeout ohne fertig zu werden"""
        print("\n  Teste: Task erreicht Timeout")
        
        task_id = "test_task_timeout"
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                # Initial status - nicht fertig
                return {
                    "success": True,
                    "data": {"finished": False}
                }
            else:
                # Alle weiteren Checks - immer noch nicht fertig
                return {
                    "success": True,
                    "data": {"finished": False}
                }
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        # Mock time.time() um Timeout zu simulieren
        start_time = time.time()
        # Simuliere, dass wir nach max_wait Sekunden sind
        time_values = [start_time]
        for i in range(200):  # Viele Polling-Zyklen
            time_values.append(start_time + i * 2)  # Jeder Polling-Zyklus dauert 2s
        time_values.append(start_time + 300)  # Timeout erreicht
        mock_time = mocker.patch('explore_syno_api.time.time', side_effect=time_values)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        print(f"    Ergebnis: {result}")
        assert result is None, "Sollte None zurückgeben bei Timeout"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_finished_at_timeout_check(self, mock_sleep, api_instance, mocker):
        """Test: Task wird beim Timeout-Check doch noch fertig"""
        print("\n  Teste: Task wird beim Timeout-Check fertig")
        
        task_id = "test_task_timeout_success"
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                return {"success": True, "data": {"finished": False}}
            else:
                # Beim Timeout-Check - doch noch fertig!
                return {
                    "success": True,
                    "data": {
                        "finished": True,
                        "num_dir": 10,
                        "num_file": 20,
                        "total_size": 100000
                    }
                }
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        # Simuliere Timeout
        start_time = time.time()
        time_values = [start_time + i * 2 for i in range(200)]  # Viele Zeitpunkte
        time_values.append(start_time + 300)  # Timeout erreicht
        mock_time = mocker.patch('explore_syno_api.time.time', side_effect=time_values)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        assert result is not None, "Sollte Ergebnis zurückgeben wenn Task beim Timeout-Check fertig wird"
        assert result['num_dir'] == 10
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_error_160_task_not_found(self, mock_sleep, api_instance, mocker):
        """Test: Fehler 160 (Task nicht gefunden) mit Retry"""
        print("\n  Teste: Fehler 160 (Task nicht gefunden) mit Retry")
        
        task_id = "test_task_160"
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                # Initial status - Task nicht gefunden
                return {
                    "success": False,
                    "error": {"code": 160, "message": "Task not found"}
                }
            elif call_count[0] == 3:
                # Retry - Task jetzt gefunden und fertig
                return {
                    "success": True,
                    "data": {
                        "finished": True,
                        "num_dir": 1,
                        "num_file": 1,
                        "total_size": 5000
                    }
                }
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        assert result is not None, "Sollte nach Retry erfolgreich sein"
        assert result['num_dir'] == 1
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_error_599_handling(self, mock_sleep, api_instance, mocker):
        """Test: Fehler 599 wird behandelt und Polling läuft weiter"""
        print("\n  Teste: Fehler 599 wird behandelt")
        
        task_id = "test_task_599"
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                # Initial status - 599 Fehler
                return {
                    "success": False,
                    "error": {"code": 599, "message": "Service unavailable"}
                }
            elif call_count[0] == 3:
                # Nach 599 - Task jetzt verfügbar und fertig
                return {
                    "success": True,
                    "data": {
                        "finished": True,
                        "num_dir": 1,
                        "num_file": 1,
                        "total_size": 5000
                    }
                }
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        assert result is not None, "Sollte nach 599-Fehler erfolgreich sein"
        assert result['num_dir'] == 1
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_shutdown_event(self, mock_sleep, api_instance, mocker):
        """Test: Shutdown-Event beendet Polling sofort"""
        print("\n  Teste: Shutdown-Event beendet Polling")
        
        task_id = "test_task_shutdown"
        shutdown_event = threading.Event()
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                # Setze Shutdown-Event nach initialem Check
                shutdown_event.set()
                return {"success": True, "data": {"finished": False}}
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2, shutdown_event=shutdown_event)
        
        assert result is None, "Sollte None zurückgeben bei Shutdown"
        assert task_id not in api_instance._active_tasks, "Task sollte entfernt werden"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_start_fails(self, mock_sleep, api_instance, mocker):
        """Test: Task-Start schlägt fehl"""
        print("\n  Teste: Task-Start schlägt fehl")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": False,
            "error": {"code": 400, "message": "Invalid path"}
        })
        
        result = api_instance.get_dir_size("/invalid_path", max_wait=300, poll_interval=2)
        
        assert result is None, "Sollte None zurückgeben bei fehlgeschlagenem Start"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_start_no_taskid(self, mock_sleep, api_instance, mocker):
        """Test: Task-Start erfolgreich, aber keine taskid"""
        print("\n  Teste: Task-Start ohne taskid")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {}  # Keine taskid
        })
        
        result = api_instance.get_dir_size("/test_folder", max_wait=300, poll_interval=2)
        
        assert result is None, "Sollte None zurückgeben wenn keine taskid vorhanden"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_empty_folder_path(self, mock_sleep, api_instance, mocker):
        """Test: Leerer Pfad wird abgelehnt"""
        print("\n  Teste: Leerer Pfad")
        
        result = api_instance.get_dir_size("", max_wait=300, poll_interval=2)
        
        assert result is None, "Sollte None zurückgeben bei leerem Pfad"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_path_normalization(self, mock_sleep, api_instance, mocker):
        """Test: Pfad wird normalisiert (ohne führendes /)"""
        print("\n  Teste: Pfad-Normalisierung")
        
        task_id = "test_task_norm"
        call_count = [0]
        captured_path = [None]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Prüfe ob Pfad normalisiert wurde
                params = kwargs.get('additional_params', {})
                path = params.get('path', '')
                captured_path[0] = path
                assert path.startswith('/'), f"Pfad sollte mit / beginnen: {path}"
                return {"success": True, "data": {"taskid": task_id}}
            elif call_count[0] == 2:
                return {
                    "success": True,
                    "data": {
                        "finished": True,
                        "num_dir": 1,
                        "num_file": 1,
                        "total_size": 1000
                    }
                }
            return None
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', side_effect=api_call_side_effect)
        
        # Pfad ohne führendes /
        result = api_instance.get_dir_size("test_folder", max_wait=300, poll_interval=2)
        
        assert result is not None, "Sollte erfolgreich sein mit normalisiertem Pfad"
        assert captured_path[0] == "/test_folder", f"Pfad sollte normalisiert sein: {captured_path[0]}"
        print("    ✓ Korrekt!")


# Pytest-Konfiguration für ausführliche Ausgabe
@pytest.fixture(scope="session", autouse=True)
def setup_test_session():
    """Setup für die gesamte Test-Session"""
    print("\n" + "=" * 70)
    print("  UNIT-TESTS FÜR get_dir_size() POLLING-LOGIK")
    print("  Mit gemockten API-Calls (keine echten Geräte nötig)")
    print("=" * 70)
    yield
    print("\n" + "=" * 70)
    print("  TEST-SESSION ABGESCHLOSSEN")
    print("=" * 70 + "\n")
