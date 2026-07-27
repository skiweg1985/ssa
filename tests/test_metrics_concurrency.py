"""Tests für die Nebenläufigkeit der Monitoring-/Metrik-Endpoints.

Hintergrund: Der Scan läuft im Event-Loop, `/health` wird per
`asyncio.to_thread` in einem Worker-Thread ausgeführt. Beide greifen auf
dieselben Dicts zu (Scan-Status, Scheduler-Jobs, Storage). Ein
"prüfen-dann-zugreifen" auf ein Dict kann dabei genau zwischen beiden
Schritten unterbrochen werden - der Monitoring-Client bekommt dann einen
Fehler statt der letzten Werte.

Zusätzlich abgesichert: Während eines laufenden Scans muss der Zeitstempel
des letzten Laufs erhalten bleiben.
"""
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.jobs_store import initialize_jobs_store
from app.services.scanner import GRACE_PERIOD_SECONDS, ScannerService
from app.services.security import reset_key_cache


class _EvictingDict(dict):
    """
    Dict, das einen Eintrag beim Lesen entfernt.

    Simuliert deterministisch das Zeitfenster, in dem ein anderer Thread den
    Eintrag genau zwischen Prüfung und Zugriff löscht. Code der Form
    ``if key in d: d[key]`` läuft damit garantiert in einen KeyError,
    ``d.get(key)`` bleibt korrekt.
    """

    def __contains__(self, key):
        present = super().__contains__(key)
        super().pop(key, None)
        return present

    def get(self, key, default=None):
        value = super().get(key, default)
        super().pop(key, None)
        return value


# ----------------------------------------------------------------------
# Scanner-Status
# ----------------------------------------------------------------------

class TestScannerState:
    def test_is_scan_running_ohne_keyerror_bei_parallelem_loeschen(self):
        """Ein zeitgleich entfernter Grace-Period-Eintrag darf nicht knallen"""
        scanner = ScannerService()
        scanner._scan_status["demo"] = {"path_status": {}}
        scanner._scan_finished_at = _EvictingDict(
            demo=datetime.now(timezone.utc) - timedelta(seconds=GRACE_PERIOD_SECONDS + 1)
        )

        # Vor dem Fix: KeyError -> Monitoring-Antwort wird zur Fehlermeldung
        assert scanner.is_scan_running("demo") is False

    def test_is_scan_running_grace_period(self):
        scanner = ScannerService()
        scanner._scan_status["demo"] = {"path_status": {}}

        scanner._scan_finished_at["demo"] = datetime.now(timezone.utc)
        assert scanner.is_scan_running("demo") is True

        scanner._scan_finished_at["demo"] = datetime.now(timezone.utc) - timedelta(
            seconds=GRACE_PERIOD_SECONDS + 1
        )
        assert scanner.is_scan_running("demo") is False
        # Abgelaufene Einträge werden aufgeräumt
        assert "demo" not in scanner._scan_finished_at
        assert "demo" not in scanner._scan_status

    def test_paralleler_zugriff_wirft_keine_ausnahmen(self):
        """Lese- und Schreibzugriffe aus mehreren Threads bleiben fehlerfrei"""
        scanner = ScannerService()
        errors = []
        stop = threading.Event()

        def readers():
            while not stop.is_set():
                try:
                    scanner.is_scan_running("demo")
                    scanner.get_scan_progress("demo")
                except Exception as e:  # pragma: no cover - nur im Fehlerfall
                    errors.append(f"{type(e).__name__}: {e}")

        def lifecycle():
            while not stop.is_set():
                try:
                    if scanner._try_start_scan("demo"):
                        scanner._set_path_status(
                            "demo",
                            "/share",
                            {"num_dir": 1, "num_file": 2, "total_size": 3,
                             "waited": 0, "finished": True},
                        )
                        scanner._mark_all_paths_finished("demo")
                        scanner._finish_scan("demo")
                        # Grace Period sofort ablaufen lassen, damit der
                        # Aufräumzweig der Leser aktiv wird
                        scanner._scan_finished_at["demo"] = (
                            datetime.now(timezone.utc)
                            - timedelta(seconds=GRACE_PERIOD_SECONDS + 1)
                        )
                except Exception as e:  # pragma: no cover - nur im Fehlerfall
                    errors.append(f"{type(e).__name__}: {e}")

        original_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)  # Thread-Wechsel erzwingen
        try:
            threads = [threading.Thread(target=readers) for _ in range(4)]
            threads.append(threading.Thread(target=lifecycle))
            for thread in threads:
                thread.start()
            stop.wait(2)
            stop.set()
            for thread in threads:
                thread.join()
        finally:
            sys.setswitchinterval(original_interval)

        assert errors == []

    def test_get_scan_progress_liefert_stabilen_snapshot(self):
        """Der laufende Scan darf ein bereits ausgeliefertes Dict nicht ändern"""
        scanner = ScannerService()
        assert scanner._try_start_scan("demo") is True
        scanner._set_path_status(
            "demo",
            "/share",
            {"num_dir": 1, "num_file": 1, "total_size": 100, "waited": 0,
             "finished": False},
        )

        snapshot = scanner.get_scan_progress("demo")
        assert snapshot["total_size"] == 100

        # Scan läuft weiter
        scanner._set_path_status(
            "demo",
            "/andere",
            {"num_dir": 5, "num_file": 5, "total_size": 900, "waited": 0,
             "finished": True},
        )

        assert snapshot["total_size"] == 100
        assert set(snapshot["path_status"]) == {"/share"}
        assert scanner.get_scan_progress("demo")["total_size"] == 1000

    def test_zweiter_start_wird_abgewiesen(self):
        scanner = ScannerService()
        assert scanner._try_start_scan("demo") is True
        assert scanner._try_start_scan("demo") is False


# ----------------------------------------------------------------------
# Scheduler
# ----------------------------------------------------------------------

class TestSchedulerJobMap:
    def test_get_job_info_ohne_keyerror_bei_parallelem_entfernen(self):
        from app.services.scheduler import SchedulerService

        scheduler = SchedulerService()
        scheduler._job_ids = _EvictingDict(demo="scan_demo")

        # Job existiert im Scheduler nicht -> None, aber ohne KeyError
        assert scheduler.get_job_info("demo") is None

    def test_get_all_jobs_waehrend_jobs_geaendert_werden(self):
        """Iteration über die Job-Map darf nicht durch parallele Änderungen brechen"""
        from app.services.scheduler import SchedulerService

        scheduler = SchedulerService()
        for i in range(50):
            scheduler._job_ids[f"job-{i}"] = f"scan_job-{i}"

        errors = []
        stop = threading.Event()

        def mutate():
            i = 0
            while not stop.is_set():
                scheduler._job_ids[f"neu-{i}"] = f"scan_neu-{i}"
                scheduler._job_ids.pop(f"neu-{i}", None)
                i += 1

        def read():
            while not stop.is_set():
                try:
                    scheduler.get_all_jobs()
                except Exception as e:  # pragma: no cover - nur im Fehlerfall
                    errors.append(f"{type(e).__name__}: {e}")

        original_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            threads = [threading.Thread(target=mutate), threading.Thread(target=read)]
            for thread in threads:
                thread.start()
            stop.wait(2)
            stop.set()
            for thread in threads:
                thread.join()
        finally:
            sys.setswitchinterval(original_interval)

        assert errors == []


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------

def _result(slug="design-scan", timestamp=None, size=1000):
    return ScanResult(
        scan_slug=slug,
        scan_name="Design Scan",
        timestamp=timestamp or datetime.now(timezone.utc),
        status="completed",
        results=[
            ScanResultItem(
                folder_name="/design",
                success=True,
                num_dir=10,
                num_file=100,
                total_size=TotalSize(bytes=size, formatted=1.0, unit="KB"),
                elapsed_time_ms=1234,
            )
        ],
    )


class TestStorageStats:
    def test_stats_waehrend_neue_scans_eintreffen(self, tmp_path):
        """Statistiken dürfen nicht brechen, wenn parallel neue Slugs entstehen"""
        import app.services.storage as storage_module

        storage = storage_module.ScanStorage(
            db_path=tmp_path / "stats.db", auto_cleanup_enabled=False
        )
        errors = []
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                storage._results[f"slug-{i}"].append(_result(slug=f"slug-{i}"))
                i += 1

        def reader():
            while not stop.is_set():
                try:
                    storage.get_storage_stats()
                except Exception as e:  # pragma: no cover - nur im Fehlerfall
                    errors.append(f"{type(e).__name__}: {e}")

        original_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
            for thread in threads:
                thread.start()
            stop.wait(2)
            stop.set()
            for thread in threads:
                thread.join()
        finally:
            sys.setswitchinterval(original_interval)

        assert errors == []


# ----------------------------------------------------------------------
# API: letzter Lauf bleibt während eines laufenden Scans sichtbar
# ----------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    monkeypatch.setenv("SSA_ADMIN_PASSWORD", "testpass123")
    reset_key_cache()

    import app.services.storage as storage_module

    test_storage = storage_module.ScanStorage(
        db_path=tmp_path / "test.db", auto_cleanup_enabled=False
    )
    monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
    initialize_jobs_store(tmp_path / "test.db")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    reset_key_cache()


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "testpass123"}
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def running_job(client, auth_headers):
    """Job mit einem gespeicherten Lauf, dessen Scan gerade läuft"""
    import app.services.storage as storage_module
    from app.services.scanner import scanner_service

    connection = client.post(
        "/api/nas-connections",
        headers=auth_headers,
        json={"name": "NAS", "host": "nas.local", "username": "u", "password": "p"},
    ).json()
    job = client.post(
        "/api/scan-jobs",
        headers=auth_headers,
        json={
            "name": "Design Scan",
            "nas_connection_id": connection["id"],
            "paths": ["/design"],
            "interval": "6h",
            "enabled": True,
        },
    ).json()

    last_run = datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)
    storage_module._storage_instance.add_result(
        job["slug"], job["name"], _result(job["slug"], last_run), "nas.local"
    )

    scanner_service._try_start_scan(job["slug"])
    try:
        yield job, last_run
    finally:
        scanner_service._running_scans.pop(job["slug"], None)
        scanner_service._scan_status.pop(job["slug"], None)
        scanner_service._scan_finished_at.pop(job["slug"], None)


class TestLastRunWaehrendLauf:
    def test_scan_detail_behaelt_last_run(self, client, auth_headers, running_job):
        job, last_run = running_job
        body = client.get(f"/api/scans/{job['slug']}", headers=auth_headers).json()

        assert body["status"] == "running"
        assert body["last_run"] is not None, (
            "last_run darf während eines laufenden Scans nicht verloren gehen"
        )
        assert datetime.fromisoformat(body["last_run"]) == last_run

    def test_scan_liste_behaelt_last_run(self, client, auth_headers, running_job):
        job, last_run = running_job
        scans = client.get("/api/scans", headers=auth_headers).json()["scans"]
        entry = next(s for s in scans if s["scan_slug"] == job["slug"])

        assert entry["status"] == "running"
        assert entry["last_run"] is not None
        assert datetime.fromisoformat(entry["last_run"]) == last_run

    def test_prtg_liefert_weiterhin_letzte_werte(self, client, auth_headers, running_job):
        job, _ = running_job
        prtg = client.get(
            f"/api/prtg/scans/{job['slug']}", headers=auth_headers
        ).json()["prtg"]

        assert "error" not in prtg
        channels = {c["channel"]: c["value"] for c in prtg["result"]}
        assert channels["Status"] == "1"  # STATUS_RUNNING
        assert channels["Gesamtgröße"] == "1000"
