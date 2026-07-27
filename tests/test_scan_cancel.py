"""Tests für den Abbruch eines laufenden Scans - auf Ebene des Scan-Laufs.

tests/test_monitor_api.py prüft Endpunkt und Flag. Hier läuft ein echter
`run_scan()`-Durchlauf gegen eine nachgebildete NAS-API, damit belegt ist,
dass der kooperative Abbruch tatsächlich greift: der Lauf endet vorzeitig,
überspringt die restlichen Pfade und wird als 'cancelled' persistiert.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from app.models.config import NASConfigYAML, ScanTaskConfigYAML


@pytest.fixture(autouse=True)
def clean_scanner_state():
    """scanner_service ist ein Prozess-Singleton - Zustand vor/nach dem Test leeren"""
    from app.services.scanner import scanner_service

    def reset():
        with scanner_service._state_lock:
            scanner_service._running_scans.clear()
            scanner_service._scan_status.clear()
            scanner_service._scan_finished_at.clear()
            scanner_service._scan_started_at.clear()
            scanner_service._cancel_requested.clear()

    reset()
    yield
    reset()


@pytest.fixture
def storage(monkeypatch, tmp_path):
    """
    Storage plus passender Job im jobs_store.

    Der Job ist nötig, weil _persist_result Ergebnisse verwirft, wenn der Job
    nicht mehr existiert (Schutz gegen verwaiste Zeilen). Ohne ihn landet auch
    ein regulärer Lauf nicht in der Historie.
    """
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")

    import app.services.storage as storage_module
    from app.services.jobs_store import initialize_jobs_store
    from app.services.security import reset_key_cache

    reset_key_cache()
    instance = storage_module.ScanStorage(
        db_path=tmp_path / "cancel.db", auto_cleanup_enabled=False
    )
    monkeypatch.setattr(storage_module, "_storage_instance", instance)
    # scanner.py hat `storage` beim Import gebunden
    monkeypatch.setattr("app.services.scanner.storage", instance)

    store = initialize_jobs_store(tmp_path / "cancel.db")
    connection = store.create_connection(
        name="NAS", host="nas.local", username="u", password="p"
    )
    store.create_job(
        name="Abbruch-Test",
        slug="abbruch-test",
        nas_connection_id=connection["id"],
        interval="6h",
        paths=["/a", "/b", "/c"],
    )

    yield instance
    reset_key_cache()


def _config(paths):
    return ScanTaskConfigYAML(
        name="Abbruch-Test",
        slug="abbruch-test",
        nas=NASConfigYAML(
            host="nas.local", username="u", password="p", port=5001,
            use_https=True, verify_ssl=False,
        ),
        paths=paths,
        interval="6h",
        enabled=True,
    )


class FakeAPI:
    """
    Minimale NAS-API. Ruft bei jedem Poll `cancel_check` auf und gibt None
    zurück, sobald abgebrochen wurde - genau wie die echte Polling-Schleife.
    """

    def __init__(self, *args, **kwargs):
        self.scanned = []
        self.stopped_tasks = []
        self.logged_out = False

    def login(self, username, password):
        return True

    @staticmethod
    def _format_size_with_unit(size_bytes):
        """Wie das Original: getrennte Bytes, Zahl und Einheit"""
        original = size_bytes
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if size_bytes < 1024.0:
                return {
                    "size_bytes": original,
                    "size_formatted": round(size_bytes, 2),
                    "unit": unit,
                }
            size_bytes /= 1024.0
        return {"size_bytes": original, "size_formatted": round(size_bytes, 2), "unit": "PB"}

    def logout(self):
        self.logged_out = True

    def cleanup_tasks(self, ignore_errors=False):
        pass

    async def close_async_session(self):
        pass

    async def get_dir_size_async(self, path, max_wait=300, poll_interval=2,
                                 status_callback=None,
                                 progress_update_callback=None,
                                 cancel_check=None):
        self.scanned.append(path)
        # Ein Poll-Durchlauf, wie im Original: erst prüfen, dann messen
        for _ in range(3):
            if cancel_check is not None and cancel_check():
                self.stopped_tasks.append(path)
                return None
            await asyncio.sleep(0)
        if status_callback:
            status_callback({
                "num_dir": 3, "num_file": 30, "total_size": 3000,
                "waited": 2, "finished": True,
            })
        return {"num_dir": 3, "num_file": 30, "total_size": 3000, "elapsed_time": 1.5}


def test_scan_completes_without_cancel(storage, monkeypatch):
    """Gegenprobe: ohne Abbruch läuft der Scan normal durch"""
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    monkeypatch.setattr(scanner_module, "SynologyAPI", FakeAPI)

    result = asyncio.run(scanner_service.run_scan(_config(["/a", "/b"])))

    assert result.status == "completed"
    assert len(result.results) == 2
    assert all(item.success for item in result.results)


def test_cancel_between_paths_skips_the_rest(storage, monkeypatch):
    """Abbruch nach dem ersten Pfad: der zweite wird nicht mehr begonnen"""
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    created = {}

    class CancelAfterFirst(FakeAPI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created["api"] = self

        async def get_dir_size_async(self, path, **kwargs):
            result = await super().get_dir_size_async(path, **kwargs)
            # Nach dem ersten fertigen Pfad den Abbruch anfordern
            scanner_service.request_cancel("abbruch-test")
            return result

    monkeypatch.setattr(scanner_module, "SynologyAPI", CancelAfterFirst)

    result = asyncio.run(scanner_service.run_scan(_config(["/a", "/b", "/c"])))

    assert result.status == "cancelled"
    assert created["api"].scanned == ["/a"], "nach dem Abbruch kein weiterer Pfad"
    assert len(result.results) == 1
    assert result.results[0].success is True, "der gemessene Pfad bleibt erhalten"
    assert "Abgebrochen" in result.error
    assert "1 von 3" in result.error


def test_cancel_during_a_path_stops_the_nas_task(storage, monkeypatch):
    """Abbruch mitten im Pfad: cancel_check greift, der NAS-Task wird gestoppt"""
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    created = {}

    class CancelDuringFirst(FakeAPI):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created["api"] = self

        async def get_dir_size_async(self, path, **kwargs):
            # Abbruch anfordern, bevor der erste Poll läuft
            scanner_service.request_cancel("abbruch-test")
            return await super().get_dir_size_async(path, **kwargs)

    monkeypatch.setattr(scanner_module, "SynologyAPI", CancelDuringFirst)

    result = asyncio.run(scanner_service.run_scan(_config(["/a", "/b"])))

    assert result.status == "cancelled"
    assert created["api"].stopped_tasks == ["/a"], (
        "der laufende DirSize-Task muss am NAS gestoppt werden"
    )
    # Der abgebrochene Pfad ist nicht erfolgreich, aber auch nicht "fehlgeschlagen"
    assert len(result.results) == 1
    assert result.results[0].success is False
    assert result.results[0].error == "Abgebrochen"


def test_cancelled_run_is_persisted_but_not_a_success(storage, monkeypatch):
    """
    Der Kern: der abgebrochene Lauf steht in der Historie, gilt aber nicht als
    erfolgreich - `last_success` bleibt auf dem vorherigen guten Lauf.
    """
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    monkeypatch.setattr(scanner_module, "SynologyAPI", FakeAPI)
    config = _config(["/a"])

    # Erst ein sauberer Lauf
    good = asyncio.run(scanner_service.run_scan(config))
    assert good.status == "completed"

    # Grace Period auflösen: ein beendeter Scan gilt noch 5 s als "laufend",
    # sonst verweigert der Doppelstart-Schutz den zweiten Lauf. Im Betrieb
    # liegen zwei Läufe ohnehin weit auseinander.
    with scanner_service._state_lock:
        scanner_service._scan_finished_at.clear()
        scanner_service._scan_status.clear()

    # Dann ein abgebrochener
    class CancelImmediately(FakeAPI):
        async def get_dir_size_async(self, path, **kwargs):
            scanner_service.request_cancel("abbruch-test")
            return await super().get_dir_size_async(path, **kwargs)

    monkeypatch.setattr(scanner_module, "SynologyAPI", CancelImmediately)
    cancelled = asyncio.run(scanner_service.run_scan(config))
    assert cancelled.status == "cancelled"

    latest = storage.get_latest_result("abbruch-test")
    assert latest is not None
    assert latest.status == "cancelled", "der Abbruch muss in der Historie stehen"

    latest_completed = storage.get_latest_completed_result("abbruch-test")
    assert latest_completed is not None
    assert latest_completed.status == "completed", (
        "der Abbruch darf den letzten erfolgreichen Lauf nicht verdrängen"
    )
    assert latest_completed.timestamp == good.timestamp


def test_run_state_is_cleaned_up_after_cancel(storage, monkeypatch):
    """Nach dem Abbruch darf kein Abbruchwunsch und keine Startzeit übrig sein"""
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    class CancelImmediately(FakeAPI):
        async def get_dir_size_async(self, path, **kwargs):
            scanner_service.request_cancel("abbruch-test")
            return await super().get_dir_size_async(path, **kwargs)

    monkeypatch.setattr(scanner_module, "SynologyAPI", CancelImmediately)
    asyncio.run(scanner_service.run_scan(_config(["/a"])))

    assert scanner_service.is_cancel_requested("abbruch-test") is False
    assert scanner_service.get_scan_started_at("abbruch-test") is None


def test_run_records_the_expected_folder_count(storage, monkeypatch):
    """
    Jeder Lauf hält fest, wie viele Ordner er scannen sollte - auch der
    abgebrochene. Sonst wäre nach einem Neustart nicht unterscheidbar, ob ein
    fehlender Ordner fehlschlug oder erst danach konfiguriert wurde.
    """
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    monkeypatch.setattr(scanner_module, "SynologyAPI", FakeAPI)
    result = asyncio.run(scanner_service.run_scan(_config(["/a", "/b", "/c"])))
    assert result.expected_folders == 3

    with scanner_service._state_lock:
        scanner_service._scan_finished_at.clear()
        scanner_service._scan_status.clear()

    class CancelImmediately(FakeAPI):
        async def get_dir_size_async(self, path, **kwargs):
            scanner_service.request_cancel("abbruch-test")
            return await super().get_dir_size_async(path, **kwargs)

    monkeypatch.setattr(scanner_module, "SynologyAPI", CancelImmediately)
    cancelled = asyncio.run(scanner_service.run_scan(_config(["/a", "/b", "/c"])))
    assert cancelled.status == "cancelled"
    assert cancelled.expected_folders == 3, (
        "auch ein abgebrochener Lauf kennt seinen Sollwert"
    )


def test_started_at_is_set_while_running(storage, monkeypatch):
    """Die Startzeit steht während des Laufs bereit - Basis der stuck-Erkennung"""
    from app.services import scanner as scanner_module
    from app.services.scanner import scanner_service

    seen = {}

    class ObserveStart(FakeAPI):
        async def get_dir_size_async(self, path, **kwargs):
            seen["started_at"] = scanner_service.get_scan_started_at("abbruch-test")
            return await super().get_dir_size_async(path, **kwargs)

    monkeypatch.setattr(scanner_module, "SynologyAPI", ObserveStart)
    before = datetime.now(timezone.utc)
    asyncio.run(scanner_service.run_scan(_config(["/a"])))

    assert seen["started_at"] is not None
    assert seen["started_at"] >= before
