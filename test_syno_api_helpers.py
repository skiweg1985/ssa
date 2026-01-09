#!/usr/bin/env python3
"""
Unit-Tests für die neuen Hilfsfunktionen der SynologyAPI-Klasse
Testet die Refactoring-Funktionen, um Einrückungsfehler zu vermeiden.

Verwendet pytest für strukturierte Tests mit ausführlichen Print-Ausgaben.
"""

import sys
import os
import time
import pytest
import threading
from unittest.mock import patch
from typing import Dict, Optional

# Füge das aktuelle Verzeichnis zum Python-Pfad hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importiere die SynologyAPI-Klasse
from explore_syno_api import SynologyAPI


@pytest.fixture
def api_instance():
    """Erstellt eine SynologyAPI-Instanz für Tests (ohne echte API-Verbindung)"""
    api = SynologyAPI.__new__(SynologyAPI)
    api.output_json = False  # Für Print-Ausgaben
    api._active_tasks = []  # Initialisiere leere Liste
    return api


class TestIsTaskFinished:
    """Test-Klasse für _is_task_finished() Funktion"""
    
    def test_boolean_true(self, api_instance, capsys):
        """Test: Boolean True sollte True zurückgeben"""
        print("\n  Teste: Boolean True")
        print(f"    Input: True (Typ: bool)")
        result = api_instance._is_task_finished(True)
        print(f"    Ergebnis: {result}")
        assert result is True, "Boolean True sollte True zurückgeben"
        print("    ✓ Korrekt!")
    
    def test_boolean_false(self, api_instance, capsys):
        """Test: Boolean False sollte False zurückgeben"""
        print("\n  Teste: Boolean False")
        print(f"    Input: False (Typ: bool)")
        result = api_instance._is_task_finished(False)
        print(f"    Ergebnis: {result}")
        assert result is False, "Boolean False sollte False zurückgeben"
        print("    ✓ Korrekt!")
    
    @pytest.mark.parametrize("value,expected,description", [
        ("true", True, "String 'true' (lowercase)"),
        ("True", True, "String 'True' (capitalized)"),
        ("TRUE", True, "String 'TRUE' (uppercase)"),
        ("1", True, "String '1'"),
        ("yes", True, "String 'yes'"),
        ("Yes", True, "String 'Yes'"),
        (1, True, "Integer 1"),
        (1.0, True, "Float 1.0"),
        (0, False, "Integer 0"),
        (0.0, False, "Float 0.0"),
        ("false", False, "String 'false'"),
        ("0", False, "String '0'"),
        ("no", False, "String 'no'"),
        (None, False, "None"),
        ("", False, "Empty string"),
        (2, False, "Integer 2"),
        (-1, False, "Integer -1"),
    ])
    def test_various_types(self, api_instance, capsys, value, expected, description):
        """Test: Verschiedene Datentypen für finished-Wert"""
        print(f"\n  Teste: {description}")
        print(f"    Input: {value!r} (Typ: {type(value).__name__})")
        print(f"    Erwartet: {expected}")
        result = api_instance._is_task_finished(value)
        print(f"    Ergebnis: {result}")
        assert result == expected, f"Erwartet {expected}, aber erhalten {result}"
        print("    ✓ Korrekt!")


class TestExtractTaskResult:
    """Test-Klasse für _extract_task_result() Funktion"""
    
    def test_normal_data(self, api_instance, capsys):
        """Test: Normale Daten mit allen Feldern"""
        print("\n  Teste: Normale Daten mit allen Feldern")
        data = {
            "num_dir": 10,
            "num_file": 25,
            "total_size": 1024000
        }
        print(f"    Input data: {data}")
        start_time = time.time()
        result = api_instance._extract_task_result(data, start_time, 42)
        print(f"    Ergebnis:")
        print(f"      num_dir: {result['num_dir']}")
        print(f"      num_file: {result['num_file']}")
        print(f"      total_size: {result['total_size']}")
        print(f"      elapsed_time: {result['elapsed_time']}s")
        assert result['num_dir'] == 10
        assert result['num_file'] == 25
        assert result['total_size'] == 1024000
        assert 'elapsed_time' in result
        print("    ✓ Korrekt!")
    
    def test_empty_data(self, api_instance, capsys):
        """Test: Leere Daten (0 Werte)"""
        print("\n  Teste: Leere Daten (0 Werte)")
        data = {
            "num_dir": 0,
            "num_file": 0,
            "total_size": 0
        }
        print(f"    Input data: {data}")
        start_time = time.time()
        result = api_instance._extract_task_result(data, start_time, 42)
        assert result['num_dir'] == 0
        assert result['num_file'] == 0
        assert result['total_size'] == 0
        print("    ✓ Korrekt!")
    
    def test_large_values(self, api_instance, capsys):
        """Test: Große Werte"""
        print("\n  Teste: Große Werte")
        data = {
            "num_dir": 100,
            "num_file": 500,
            "total_size": 1073741824  # 1 GB
        }
        print(f"    Input data: {data}")
        start_time = time.time()
        result = api_instance._extract_task_result(data, start_time, 42)
        assert result['num_dir'] == 100
        assert result['num_file'] == 500
        assert result['total_size'] == 1073741824
        print("    ✓ Korrekt!")
    
    def test_missing_num_file(self, api_instance, capsys):
        """Test: Fehlende Felder (num_file)"""
        print("\n  Teste: Fehlende Felder (num_file)")
        data = {
            "num_dir": 5,
            "total_size": 50000
        }
        print(f"    Input data: {data}")
        start_time = time.time()
        result = api_instance._extract_task_result(data, start_time, 42)
        assert result['num_dir'] == 5
        assert result['num_file'] == 0  # Default-Wert
        assert result['total_size'] == 50000
        print("    ✓ Korrekt!")
    
    def test_missing_num_dir(self, api_instance, capsys):
        """Test: Fehlende Felder (num_dir)"""
        print("\n  Teste: Fehlende Felder (num_dir)")
        data = {
            "num_file": 3,
            "total_size": 1000
        }
        print(f"    Input data: {data}")
        start_time = time.time()
        result = api_instance._extract_task_result(data, start_time, 42)
        assert result['num_dir'] == 0  # Default-Wert
        assert result['num_file'] == 3
        assert result['total_size'] == 1000
        print("    ✓ Korrekt!")
    
    def test_empty_dict(self, api_instance, capsys):
        """Test: Leeres Dictionary"""
        print("\n  Teste: Leeres Dictionary")
        data = {}
        print(f"    Input data: {data}")
        start_time = time.time()
        result = api_instance._extract_task_result(data, start_time, 42)
        assert result['num_dir'] == 0
        assert result['num_file'] == 0
        assert result['total_size'] == 0
        assert 'elapsed_time' in result
        print("    ✓ Korrekt!")


class TestCheckAndHandleFinishedTask:
    """Test-Klasse für _check_and_handle_finished_task() Funktion"""
    
    def test_finished_true(self, api_instance, capsys):
        """Test: Erfolgreiche Response mit finished=True"""
        print("\n  Teste: Erfolgreiche Response mit finished=True")
        status_response = {
            "success": True,
            "data": {
                "finished": True,
                "num_dir": 5,
                "num_file": 10,
                "total_size": 50000
            }
        }
        print(f"    Input status_response: {status_response}")
        api_instance._active_tasks = ["test_task_123"]
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        print(f"    Ergebnis: {result}")
        print(f"    Typ: {type(result).__name__}")
        print(f"    _active_tasks nachher: {len(api_instance._active_tasks)}")
        assert isinstance(result, dict)
        assert result['num_dir'] == 5
        assert result['num_file'] == 10
        assert result['total_size'] == 50000
        assert "test_task_123" not in api_instance._active_tasks
        print("    ✓ Korrekt!")
    
    def test_finished_string_true(self, api_instance, capsys):
        """Test: Erfolgreiche Response mit finished='true' (String)"""
        print("\n  Teste: Erfolgreiche Response mit finished='true' (String)")
        status_response = {
            "success": True,
            "data": {
                "finished": "true",
                "num_dir": 3,
                "num_file": 7,
                "total_size": 30000
            }
        }
        print(f"    Input status_response: {status_response}")
        api_instance._active_tasks = ["test_task_123"]
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        assert isinstance(result, dict)
        assert result['num_dir'] == 3
        assert "test_task_123" not in api_instance._active_tasks
        print("    ✓ Korrekt!")
    
    def test_finished_integer_one(self, api_instance, capsys):
        """Test: Erfolgreiche Response mit finished=1 (Integer)"""
        print("\n  Teste: Erfolgreiche Response mit finished=1 (Integer)")
        status_response = {
            "success": True,
            "data": {
                "finished": 1,
                "num_dir": 2,
                "num_file": 4,
                "total_size": 20000
            }
        }
        print(f"    Input status_response: {status_response}")
        api_instance._active_tasks = ["test_task_123"]
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        assert isinstance(result, dict)
        assert result['num_dir'] == 2
        print("    ✓ Korrekt!")
    
    def test_finished_false(self, api_instance, capsys):
        """Test: Erfolgreiche Response mit finished=False"""
        print("\n  Teste: Erfolgreiche Response mit finished=False")
        status_response = {
            "success": True,
            "data": {
                "finished": False,
                "num_dir": 1,
                "num_file": 2,
                "total_size": 10000
            }
        }
        print(f"    Input status_response: {status_response}")
        api_instance._active_tasks = []
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        print(f"    Ergebnis: {result}")
        assert result is None
        print("    ✓ Korrekt!")
    
    def test_finished_string_false(self, api_instance, capsys):
        """Test: Erfolgreiche Response mit finished='false' (String)"""
        print("\n  Teste: Erfolgreiche Response mit finished='false' (String)")
        status_response = {
            "success": True,
            "data": {
                "finished": "false",
                "num_dir": 1,
                "num_file": 2,
                "total_size": 10000
            }
        }
        print(f"    Input status_response: {status_response}")
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        assert result is None
        print("    ✓ Korrekt!")
    
    def test_failed_response(self, api_instance, capsys):
        """Test: Fehlgeschlagene Response (success=False)"""
        print("\n  Teste: Fehlgeschlagene Response (success=False)")
        status_response = {
            "success": False,
            "error": {
                "code": 160,
                "message": "Task not found"
            }
        }
        print(f"    Input status_response: {status_response}")
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        assert result is None
        print("    ✓ Korrekt!")
    
    def test_none_response(self, api_instance, capsys):
        """Test: None Response"""
        print("\n  Teste: None Response")
        status_response = None
        print(f"    Input status_response: {status_response}")
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        assert result is None
        print("    ✓ Korrekt!")
    
    def test_empty_dict_response(self, api_instance, capsys):
        """Test: Leeres Dictionary"""
        print("\n  Teste: Leeres Dictionary")
        status_response = {}
        print(f"    Input status_response: {status_response}")
        start_time = time.time()
        result = api_instance._check_and_handle_finished_task(
            status_response, "test_task_123", start_time, 30
        )
        assert result is None
        print("    ✓ Korrekt!")


class TestStartDirSizeTask:
    """Test-Klasse für _start_dir_size_task() Funktion"""
    
    @patch('explore_syno_api.time.sleep')
    def test_successful_start(self, mock_sleep, api_instance, mocker):
        """Test: Erfolgreicher Task-Start"""
        print("\n  Teste: Erfolgreicher Task-Start")
        task_id = "test_task_123"
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {"taskid": task_id}
        })
        
        result = api_instance._start_dir_size_task("/test_folder")
        
        assert result == task_id, f"Sollte task_id zurückgeben: {task_id}"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_failed_start(self, mock_sleep, api_instance, mocker):
        """Test: Fehlgeschlagener Task-Start"""
        print("\n  Teste: Fehlgeschlagener Task-Start")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": False,
            "error": {"code": 400, "message": "Invalid path"}
        })
        
        result = api_instance._start_dir_size_task("/invalid_path")
        
        assert result is None, "Sollte None zurückgeben bei fehlgeschlagenem Start"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_no_response(self, mock_sleep, api_instance, mocker):
        """Test: Keine Antwort vom Server"""
        print("\n  Teste: Keine Antwort vom Server")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value=None)
        
        result = api_instance._start_dir_size_task("/test_folder")
        
        assert result is None, "Sollte None zurückgeben wenn keine Antwort"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_no_taskid(self, mock_sleep, api_instance, mocker):
        """Test: Erfolgreicher Start, aber keine taskid"""
        print("\n  Teste: Erfolgreicher Start ohne taskid")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {}  # Keine taskid
        })
        
        result = api_instance._start_dir_size_task("/test_folder")
        
        assert result is None, "Sollte None zurückgeben wenn keine taskid vorhanden"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_empty_taskid(self, mock_sleep, api_instance, mocker):
        """Test: Leere taskid"""
        print("\n  Teste: Leere taskid")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {"taskid": ""}  # Leere taskid
        })
        
        result = api_instance._start_dir_size_task("/test_folder")
        
        assert result is None, "Sollte None zurückgeben bei leerer taskid"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_whitespace_taskid(self, mock_sleep, api_instance, mocker):
        """Test: taskid nur mit Whitespace"""
        print("\n  Teste: taskid nur mit Whitespace")
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {"taskid": "   "}  # Nur Whitespace
        })
        
        result = api_instance._start_dir_size_task("/test_folder")
        
        assert result is None, "Sollte None zurückgeben bei taskid nur mit Whitespace"
        print("    ✓ Korrekt!")


class TestHandleInitialStatusCheck:
    """Test-Klasse für _handle_initial_status_check() Funktion"""
    
    @patch('explore_syno_api.time.sleep')
    def test_task_finished_immediately(self, mock_sleep, api_instance, mocker):
        """Test: Task ist beim initialen Check bereits fertig"""
        print("\n  Teste: Task ist beim initialen Check bereits fertig")
        task_id = "test_task_123"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        
        initial_status = {
            "success": True,
            "data": {
                "finished": True,
                "num_dir": 5,
                "num_file": 10,
                "total_size": 50000
            }
        }
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is not None, "Sollte Ergebnis zurückgeben wenn Task fertig"
        assert result['num_dir'] == 5
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_task_not_finished(self, mock_sleep, api_instance, mocker):
        """Test: Task ist noch nicht fertig"""
        print("\n  Teste: Task ist noch nicht fertig")
        task_id = "test_task_456"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        
        initial_status = {
            "success": True,
            "data": {
                "finished": False,
                "progress": 0.3
            }
        }
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is None, "Sollte None zurückgeben wenn Task nicht fertig"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_error_160_with_retry_success(self, mock_sleep, api_instance, mocker):
        """Test: Fehler 160 mit erfolgreichem Retry"""
        print("\n  Teste: Fehler 160 mit erfolgreichem Retry")
        task_id = "test_task_160"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        call_count = [0]
        
        def api_call_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Retry-Status-Check - erfolgreich
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
        
        initial_status = {
            "success": False,
            "error": {"code": 160, "message": "Task not found"}
        }
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is not None, "Sollte Ergebnis zurückgeben nach erfolgreichem Retry"
        assert result['num_dir'] == 1
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_error_160_with_retry_failure(self, mock_sleep, api_instance, mocker):
        """Test: Fehler 160 mit fehlgeschlagenem Retry"""
        print("\n  Teste: Fehler 160 mit fehlgeschlagenem Retry")
        task_id = "test_task_160_fail"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        api_instance._active_tasks = [task_id]
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": False,
            "error": {"code": 160, "message": "Task not found"}
        })
        
        initial_status = {
            "success": False,
            "error": {"code": 160, "message": "Task not found"}
        }
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is None, "Sollte None zurückgeben wenn Retry fehlschlägt"
        assert task_id not in api_instance._active_tasks, "Task sollte entfernt werden"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_error_599(self, mock_sleep, api_instance, mocker):
        """Test: Fehler 599 wird behandelt"""
        print("\n  Teste: Fehler 599 wird behandelt")
        task_id = "test_task_599"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        
        initial_status = {
            "success": False,
            "error": {"code": 599, "message": "Service unavailable"}
        }
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is None, "Sollte None zurückgeben bei 599-Fehler"
        assert error_599_count[0] == 1, "error_599_count sollte auf 1 gesetzt werden"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_other_error(self, mock_sleep, api_instance, mocker):
        """Test: Anderer Fehler"""
        print("\n  Teste: Anderer Fehler")
        task_id = "test_task_other"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        
        initial_status = {
            "success": False,
            "error": {"code": 500, "message": "Internal server error"}
        }
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is None, "Sollte None zurückgeben bei anderem Fehler"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_none_response(self, mock_sleep, api_instance, mocker):
        """Test: None Response"""
        print("\n  Teste: None Response")
        task_id = "test_task_none"
        start_time = time.time()
        waited = 0
        error_599_count = [0]
        
        initial_status = None
        
        result = api_instance._handle_initial_status_check(
            initial_status, task_id, start_time, waited, error_599_count
        )
        
        assert result is None, "Sollte None zurückgeben bei None-Response"
        print("    ✓ Korrekt!")


class TestCheckTimeoutAndFinalStatus:
    """Test-Klasse für _check_timeout_and_final_status() Funktion"""
    
    @patch('explore_syno_api.time.sleep')
    def test_timeout_not_reached(self, mock_sleep, api_instance, mocker):
        """Test: Timeout noch nicht erreicht"""
        print("\n  Teste: Timeout noch nicht erreicht")
        task_id = "test_task_123"
        waited = 100
        max_wait = 300
        start_time = time.time()
        
        result = api_instance._check_timeout_and_final_status(
            task_id, waited, max_wait, start_time
        )
        
        assert result is None, "Sollte None zurückgeben wenn Timeout nicht erreicht"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_timeout_reached_task_finished(self, mock_sleep, api_instance, mocker):
        """Test: Timeout erreicht, Task ist fertig"""
        print("\n  Teste: Timeout erreicht, Task ist fertig")
        task_id = "test_task_timeout_success"
        waited = 300
        max_wait = 300
        start_time = time.time()
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {
                "finished": True,
                "num_dir": 10,
                "num_file": 20,
                "total_size": 100000
            }
        })
        
        result = api_instance._check_timeout_and_final_status(
            task_id, waited, max_wait, start_time
        )
        
        assert result is not None, "Sollte Ergebnis zurückgeben wenn Task beim Timeout-Check fertig"
        assert result['num_dir'] == 10
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_timeout_reached_task_not_finished(self, mock_sleep, api_instance, mocker):
        """Test: Timeout erreicht, Task ist nicht fertig"""
        print("\n  Teste: Timeout erreicht, Task ist nicht fertig")
        task_id = "test_task_timeout_fail"
        waited = 300
        max_wait = 300
        start_time = time.time()
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value={
            "success": True,
            "data": {
                "finished": False
            }
        })
        
        result = api_instance._check_timeout_and_final_status(
            task_id, waited, max_wait, start_time
        )
        
        assert result is None, "Sollte None zurückgeben wenn Task nicht fertig"
        print("    ✓ Korrekt!")
    
    @patch('explore_syno_api.time.sleep')
    def test_timeout_reached_no_response(self, mock_sleep, api_instance, mocker):
        """Test: Timeout erreicht, keine Response"""
        print("\n  Teste: Timeout erreicht, keine Response")
        task_id = "test_task_timeout_no_response"
        waited = 300
        max_wait = 300
        start_time = time.time()
        
        mock_api_call = mocker.patch.object(api_instance, '_api_call', return_value=None)
        
        result = api_instance._check_timeout_and_final_status(
            task_id, waited, max_wait, start_time
        )
        
        assert result is None, "Sollte None zurückgeben wenn keine Response"
        print("    ✓ Korrekt!")


class TestUpdatePollingInterval:
    """Test-Klasse für _update_polling_interval() Funktion"""
    
    def test_progress_detected_reset_interval(self, api_instance, capsys):
        """Test: Fortschritt erkannt - Intervall wird zurückgesetzt"""
        print("\n  Teste: Fortschritt erkannt - Intervall zurückgesetzt")
        data = {"progress": 0.6, "processed_num": 20}
        current_interval = 6
        min_interval = 2
        max_interval = 10
        last_progress = 0.3
        no_progress_count = 2
        
        new_interval, new_last_progress, new_no_progress_count = api_instance._update_polling_interval(
            data, current_interval, min_interval, max_interval, last_progress, no_progress_count
        )
        
        assert new_interval == min_interval, f"Sollte auf {min_interval} zurückgesetzt werden"
        assert new_no_progress_count == 0, "no_progress_count sollte zurückgesetzt werden"
        print("    ✓ Korrekt!")
    
    def test_no_progress_increase_interval(self, api_instance, capsys):
        """Test: Kein Fortschritt - Intervall wird erhöht"""
        print("\n  Teste: Kein Fortschritt - Intervall erhöht")
        data = {"progress": 0.3, "processed_num": 10}
        current_interval = 2
        min_interval = 2
        max_interval = 10
        last_progress = 0.3  # Gleicher Wert = kein Fortschritt
        no_progress_count = 3  # Genug für Erhöhung
        
        new_interval, new_last_progress, new_no_progress_count = api_instance._update_polling_interval(
            data, current_interval, min_interval, max_interval, last_progress, no_progress_count
        )
        
        assert new_interval == 4, f"Sollte auf 4 erhöht werden (2 + 2)"
        assert new_no_progress_count == 4, "no_progress_count sollte erhöht werden"
        assert new_last_progress == 0.3, "last_progress sollte aktualisiert werden"
        print("    ✓ Korrekt!")
    
    def test_no_progress_max_interval_reached(self, api_instance, capsys):
        """Test: Kein Fortschritt, aber Max-Intervall erreicht"""
        print("\n  Teste: Kein Fortschritt, Max-Intervall erreicht")
        data = {"progress": 0.3, "processed_num": 10}
        current_interval = 10
        min_interval = 2
        max_interval = 10
        last_progress = 0.3
        no_progress_count = 3
        
        new_interval, new_last_progress, new_no_progress_count = api_instance._update_polling_interval(
            data, current_interval, min_interval, max_interval, last_progress, no_progress_count
        )
        
        assert new_interval == 10, "Sollte bei Max-Intervall bleiben"
        assert new_no_progress_count == 4, "no_progress_count sollte erhöht werden"
        print("    ✓ Korrekt!")
    
    def test_no_progress_count_too_low(self, api_instance, capsys):
        """Test: Kein Fortschritt, no_progress_count wird erhöht und erreicht 3"""
        print("\n  Teste: Kein Fortschritt, no_progress_count wird erhöht")
        data = {"progress": 0.3, "processed_num": 10}
        current_interval = 2
        min_interval = 2
        max_interval = 10
        last_progress = 0.3
        no_progress_count = 2  # Wird auf 3 erhöht, dann wird Intervall erhöht
        
        new_interval, new_last_progress, new_no_progress_count = api_instance._update_polling_interval(
            data, current_interval, min_interval, max_interval, last_progress, no_progress_count
        )
        
        # no_progress_count wird auf 3 erhöht, was >= 3 ist, also wird Intervall erhöht
        assert new_interval == 4, "Sollte erhöht werden wenn no_progress_count >= 3 wird"
        assert new_no_progress_count == 3, "no_progress_count sollte auf 3 erhöht werden"
        print("    ✓ Korrekt!")
    
    def test_first_progress_check(self, api_instance, capsys):
        """Test: Erster Fortschritts-Check (last_progress ist None)"""
        print("\n  Teste: Erster Fortschritts-Check")
        data = {"progress": 0.3, "processed_num": 10}
        current_interval = 2
        min_interval = 2
        max_interval = 10
        last_progress = None
        no_progress_count = 0
        
        new_interval, new_last_progress, new_no_progress_count = api_instance._update_polling_interval(
            data, current_interval, min_interval, max_interval, last_progress, no_progress_count
        )
        
        assert new_interval == 2, "Sollte unverändert bleiben"
        assert new_last_progress == 0.3, "last_progress sollte gesetzt werden"
        print("    ✓ Korrekt!")
    
    def test_progress_with_processed_num(self, api_instance, capsys):
        """Test: Fortschritt basierend auf processed_num"""
        print("\n  Teste: Fortschritt basierend auf processed_num")
        data = {"progress": None, "processed_num": 25}
        current_interval = 6
        min_interval = 2
        max_interval = 10
        last_progress = 20
        no_progress_count = 2
        
        new_interval, new_last_progress, new_no_progress_count = api_instance._update_polling_interval(
            data, current_interval, min_interval, max_interval, last_progress, no_progress_count
        )
        
        assert new_interval == min_interval, "Sollte zurückgesetzt werden bei Fortschritt"
        assert new_no_progress_count == 0
        print("    ✓ Korrekt!")


class TestProcessStatusResponse:
    """Test-Klasse für _process_status_response() Funktion"""
    
    def test_successful_response_with_progress(self, api_instance, capsys):
        """Test: Erfolgreiche Response mit Fortschritt"""
        print("\n  Teste: Erfolgreiche Response mit Fortschritt")
        status_response = {
            "success": True,
            "data": {
                "progress": 0.5,
                "processed_num": 20,
                "total": 40
            }
        }
        task_id = "test_task_123"
        waited = 15
        current_poll_interval = 2
        min_poll_interval = 2
        max_poll_interval = 10
        last_progress = 0.3
        no_progress_count = 0
        last_status_print = 0
        
        new_interval, new_last_progress, new_no_progress_count, new_last_status_print = api_instance._process_status_response(
            status_response, task_id, waited, current_poll_interval,
            min_poll_interval, max_poll_interval, last_progress,
            no_progress_count, last_status_print
        )
        
        assert new_interval == min_poll_interval, "Sollte auf min_interval zurückgesetzt werden bei Fortschritt"
        assert new_last_progress == 0.5, "last_progress sollte aktualisiert werden"
        assert new_no_progress_count == 0, "no_progress_count sollte zurückgesetzt werden"
        print("    ✓ Korrekt!")
    
    def test_successful_response_no_progress(self, api_instance, capsys):
        """Test: Erfolgreiche Response ohne Fortschritt"""
        print("\n  Teste: Erfolgreiche Response ohne Fortschritt")
        status_response = {
            "success": True,
            "data": {
                "progress": 0.3,
                "processed_num": 10
            }
        }
        task_id = "test_task_456"
        waited = 25
        current_poll_interval = 2
        min_poll_interval = 2
        max_poll_interval = 10
        last_progress = 0.3
        no_progress_count = 3
        last_status_print = 0
        
        new_interval, new_last_progress, new_no_progress_count, new_last_status_print = api_instance._process_status_response(
            status_response, task_id, waited, current_poll_interval,
            min_poll_interval, max_poll_interval, last_progress,
            no_progress_count, last_status_print
        )
        
        assert new_interval == 4, "Sollte erhöht werden bei keinem Fortschritt"
        assert new_no_progress_count == 4, "no_progress_count sollte erhöht werden"
        print("    ✓ Korrekt!")
    
    def test_failed_response(self, api_instance, capsys):
        """Test: Fehlgeschlagene Response"""
        print("\n  Teste: Fehlgeschlagene Response")
        status_response = {
            "success": False,
            "error": {"code": 500}
        }
        task_id = "test_task_789"
        waited = 10
        current_poll_interval = 2
        min_poll_interval = 2
        max_poll_interval = 10
        last_progress = 0.3
        no_progress_count = 1
        last_status_print = 0
        
        new_interval, new_last_progress, new_no_progress_count, new_last_status_print = api_instance._process_status_response(
            status_response, task_id, waited, current_poll_interval,
            min_poll_interval, max_poll_interval, last_progress,
            no_progress_count, last_status_print
        )
        
        assert new_interval == current_poll_interval, "Sollte unverändert bleiben bei fehlgeschlagener Response"
        assert new_no_progress_count == no_progress_count, "no_progress_count sollte unverändert bleiben"
        print("    ✓ Korrekt!")
    
    def test_none_response(self, api_instance, capsys):
        """Test: None Response"""
        print("\n  Teste: None Response")
        status_response = None
        task_id = "test_task_none"
        waited = 10
        current_poll_interval = 2
        min_poll_interval = 2
        max_poll_interval = 10
        last_progress = 0.3
        no_progress_count = 1
        last_status_print = 0
        
        new_interval, new_last_progress, new_no_progress_count, new_last_status_print = api_instance._process_status_response(
            status_response, task_id, waited, current_poll_interval,
            min_poll_interval, max_poll_interval, last_progress,
            no_progress_count, last_status_print
        )
        
        assert new_interval == current_poll_interval, "Sollte unverändert bleiben bei None-Response"
        print("    ✓ Korrekt!")


class TestCheckShutdownAndCleanup:
    """Test-Klasse für _check_shutdown_and_cleanup() Funktion"""
    
    def test_shutdown_not_set(self, api_instance, capsys):
        """Test: Shutdown-Event nicht gesetzt"""
        print("\n  Teste: Shutdown-Event nicht gesetzt")
        shutdown_event = threading.Event()
        task_id = "test_task_123"
        api_instance._active_tasks = [task_id]
        
        result = api_instance._check_shutdown_and_cleanup(shutdown_event, task_id)
        
        assert result is False, "Sollte False zurückgeben wenn Shutdown nicht gesetzt"
        assert task_id in api_instance._active_tasks, "Task sollte nicht entfernt werden"
        print("    ✓ Korrekt!")
    
    def test_shutdown_set(self, api_instance, capsys):
        """Test: Shutdown-Event gesetzt"""
        print("\n  Teste: Shutdown-Event gesetzt")
        shutdown_event = threading.Event()
        shutdown_event.set()
        task_id = "test_task_456"
        api_instance._active_tasks = [task_id]
        
        result = api_instance._check_shutdown_and_cleanup(shutdown_event, task_id)
        
        assert result is True, "Sollte True zurückgeben wenn Shutdown gesetzt"
        assert task_id not in api_instance._active_tasks, "Task sollte entfernt werden"
        print("    ✓ Korrekt!")
    
    def test_shutdown_none(self, api_instance, capsys):
        """Test: Shutdown-Event ist None"""
        print("\n  Teste: Shutdown-Event ist None")
        shutdown_event = None
        task_id = "test_task_789"
        api_instance._active_tasks = [task_id]
        
        result = api_instance._check_shutdown_and_cleanup(shutdown_event, task_id)
        
        assert result is False, "Sollte False zurückgeben wenn Shutdown None ist"
        assert task_id in api_instance._active_tasks, "Task sollte nicht entfernt werden"
        print("    ✓ Korrekt!")
    
    def test_task_not_in_active_tasks(self, api_instance, capsys):
        """Test: Task-ID nicht in _active_tasks"""
        print("\n  Teste: Task-ID nicht in _active_tasks")
        shutdown_event = threading.Event()
        shutdown_event.set()
        task_id = "test_task_not_in_list"
        api_instance._active_tasks = []  # Leere Liste
        
        result = api_instance._check_shutdown_and_cleanup(shutdown_event, task_id)
        
        assert result is True, "Sollte True zurückgeben auch wenn Task nicht in Liste"
        # Sollte keinen Fehler werfen wenn Task nicht in Liste ist
        print("    ✓ Korrekt!")


# Pytest-Konfiguration für ausführliche Ausgabe
@pytest.fixture(scope="session", autouse=True)
def setup_test_session():
    """Setup für die gesamte Test-Session"""
    print("\n" + "=" * 70)
    print("  UNIT-TESTS FÜR SYNOLOGY API HELPER-FUNKTIONEN")
    print("  Refactoring-Tests zur Vermeidung von Einrückungsfehlern")
    print("  (pytest mit ausführlichen Print-Ausgaben)")
    print("=" * 70)
    yield
    print("\n" + "=" * 70)
    print("  TEST-SESSION ABGESCHLOSSEN")
    print("=" * 70 + "\n")
