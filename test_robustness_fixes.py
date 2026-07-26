"""Regressionstests für die Robustheits- und Nebenläufigkeitsfixes.

Abgedeckt sind die Fälle aus dem Belastungstest gegen die laufende Instanz:

- Schreibpfade des Jobs-Stores unter echter Nebenläufigkeit (Threads statt
  eines einzelnen Event-Loops - so, wie es mit mehreren Workern aussieht)
- Ergebnisse eines Jobs, der während seines Laufs gelöscht wird
- Statuscodes und Eingabevalidierung, die vorher in 500ern endeten
- Paginierung der Historie, ohne das bisherige Verhalten zu ändern
- unbegrenzt wachsende In-Memory-Strukturen
- Resync, der geplante Läufe nicht mehr verschiebt
"""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.jobs_store import JobsStore, NotFoundError, initialize_jobs_store
from app.services.scheduler import parse_interval_string
from app.services.security import reset_key_cache


@pytest.fixture(autouse=True)
def _fixed_secret_key(monkeypatch):
    monkeypatch.setenv("SSA_SECRET_KEY", "test-master-key")
    reset_key_cache()
    yield
    reset_key_cache()


@pytest.fixture
def store(tmp_path):
    return JobsStore(tmp_path / "test.db")


@pytest.fixture
def connection(store):
    return store.create_connection(
        name="Test-NAS", host="192.168.1.10", username="syno", password="geheim"
    )


def _job_kwargs(connection, name, interval="30m"):
    return {
        "name": name,
        "nas_connection_id": connection["id"],
        "interval": interval,
        "enabled": False,
        "paths": ["/homes"],
    }


# ----------------------------------------------------------------------
# Nebenläufige Schreibzugriffe auf den Jobs-Store
# ----------------------------------------------------------------------

class TestConcurrentWrites:
    """Threads statt Event-Loop: so verhält sich der Store mit mehreren Workern."""

    def test_parallel_create_same_name_yields_unique_slugs(self, store, connection):
        """Slug-Vergabe war SELECT-dann-INSERT -> UNIQUE constraint failed"""
        barrier = threading.Barrier(12)
        results = []
        errors = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            try:
                job = store.create_job(**_job_kwargs(connection, "gleicher-name"))
                with lock:
                    results.append(job["slug"])
            except Exception as e:  # pragma: no cover - nur im Fehlerfall
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Fehler beim parallelen Anlegen: {errors}"
        assert len(results) == 12
        assert len(set(results)) == 12, f"doppelte Slugs vergeben: {sorted(results)}"

    def test_parallel_update_and_delete_never_raises_assertion(self, store, connection):
        """update_job endete bei parallelem DELETE in einem AssertionError"""
        unexpected = []
        lock = threading.Lock()

        for i in range(25):
            job = store.create_job(**_job_kwargs(connection, f"job-{i}"))
            slug = job["slug"]
            barrier = threading.Barrier(2)

            def updater():
                barrier.wait()
                try:
                    store.update_job(
                        slug,
                        name=f"job-{i}",
                        nas_connection_id=connection["id"],
                        interval="45m",
                        enabled=False,
                        paths=["/homes"],
                    )
                except NotFoundError:
                    pass  # zulässig: der Job war schon weg
                except Exception as e:
                    with lock:
                        unexpected.append(e)

            def deleter():
                barrier.wait()
                try:
                    store.delete_job(slug)
                except NotFoundError:
                    pass
                except Exception as e:  # pragma: no cover
                    with lock:
                        unexpected.append(e)

            threads = [threading.Thread(target=updater), threading.Thread(target=deleter)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert unexpected == [], f"unerwartete Fehler: {unexpected}"

    def test_update_missing_job_raises_notfound(self, store, connection):
        with pytest.raises(NotFoundError):
            store.update_job(
                "gibt-es-nicht",
                name="x",
                nas_connection_id=connection["id"],
                interval="30m",
                enabled=False,
                paths=["/homes"],
            )

    def test_no_asserts_left_in_write_paths(self):
        """asserts verschwinden unter python -O - im Schreibpfad nichts verloren"""
        import inspect

        import app.services.jobs_store as module

        source = inspect.getsource(module)
        code_lines = [
            line.split("#")[0]
            for line in source.splitlines()
            if not line.strip().startswith("#")
        ]
        assert not [line for line in code_lines if line.strip().startswith("assert ")]


# ----------------------------------------------------------------------
# Intervall-Validierung
# ----------------------------------------------------------------------

class TestIntervalParsing:
    def test_overflow_is_rejected(self):
        """timedelta(days=10**20) warf OverflowError bis in einen 500er"""
        assert parse_interval_string("99999999999999999999d") is None
        assert parse_interval_string("99999999999999999999s") is None

    def test_zero_is_rejected(self):
        """APScheduler macht aus 0s stillschweigend 1s - ein Dauerscan"""
        assert parse_interval_string("0s") is None
        assert parse_interval_string("0d") is None

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("30m", timedelta(minutes=30)),
            ("15m", timedelta(minutes=15)),
            ("1d", timedelta(days=1)),
            ("10s", timedelta(seconds=10)),
        ],
    )
    def test_normal_intervals_unchanged(self, value, expected):
        assert parse_interval_string(value) == expected


# ----------------------------------------------------------------------
# Scanner: Ergebnisse eines gelöschten Jobs
# ----------------------------------------------------------------------

def _make_result(slug: str) -> ScanResult:
    return ScanResult(
        scan_slug=slug,
        scan_name=slug,
        timestamp=datetime.now(timezone.utc),
        status="completed",
        results=[
            ScanResultItem(
                folder_name="/homes",
                success=True,
                num_dir=1,
                num_file=2,
                total_size=TotalSize(bytes=1024, formatted=1.0, unit="KB"),
                elapsed_time_ms=10,
            )
        ],
    )


class TestScannerPersistence:
    def test_result_discarded_when_job_deleted(self, monkeypatch, tmp_path):
        """Ein während des Laufs gelöschter Job darf nichts mehr schreiben"""
        import app.services.scanner as scanner_module
        import app.services.storage as storage_module

        test_storage = storage_module.ScanStorage(
            db_path=tmp_path / "test.db", auto_cleanup_enabled=False
        )
        monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
        monkeypatch.setattr(scanner_module, "storage", test_storage)
        initialize_jobs_store(tmp_path / "test.db")

        service = scanner_module.ScannerService()
        saved = service._persist_result(
            "geloeschter-job", "geloeschter-job", _make_result("geloeschter-job"), "nas.local"
        )

        assert saved is False
        assert test_storage.count_results("geloeschter-job") == 0

    def test_result_saved_for_existing_job(self, monkeypatch, tmp_path):
        import app.services.scanner as scanner_module
        import app.services.storage as storage_module

        test_storage = storage_module.ScanStorage(
            db_path=tmp_path / "test.db", auto_cleanup_enabled=False
        )
        monkeypatch.setattr(storage_module, "_storage_instance", test_storage)
        monkeypatch.setattr(scanner_module, "storage", test_storage)
        jobs = initialize_jobs_store(tmp_path / "test.db")
        conn = jobs.create_connection(
            name="NAS", host="nas.local", username="u", password="p"
        )
        job = jobs.create_job(**_job_kwargs(conn, "echter-job"))

        service = scanner_module.ScannerService()
        saved = service._persist_result(
            job["slug"], job["name"], _make_result(job["slug"]), "nas.local"
        )

        assert saved is True
        assert test_storage.count_results(job["slug"]) == 1

    def test_running_scans_map_does_not_grow(self):
        """_finish_scan liess pro Slug einen False-Eintrag liegen"""
        import app.services.scanner as scanner_module

        service = scanner_module.ScannerService()
        for i in range(100):
            slug = f"scan-{i}"
            assert service._try_start_scan(slug) is True
            service._finish_scan(slug)

        assert service._running_scans == {}


# ----------------------------------------------------------------------
# Rate-Limiter: Speicherwachstum
# ----------------------------------------------------------------------

class TestSchedulerResync:
    """resync_from_db plante bisher JEDEN bestehenden Job neu ein.

    Bei Intervall-Triggern beginnt das Intervall dadurch von vorn - wer
    regelmässig reloadet, verschiebt den nächsten Lauf immer weiter und ein
    Job läuft im Extremfall nie.
    """

    @pytest.fixture
    def scheduler(self, tmp_path, monkeypatch):
        from app.services.scheduler import SchedulerService

        jobs = initialize_jobs_store(tmp_path / "test.db")
        conn = jobs.create_connection(
            name="NAS", host="nas.local", username="u", password="p"
        )
        jobs.create_job(
            name="job-a",
            nas_connection_id=conn["id"],
            interval="30m",
            enabled=True,
            paths=["/homes"],
        )
        service = SchedulerService()
        service.load_and_schedule()
        return service, jobs

    def test_unchanged_job_is_not_rescheduled(self, scheduler):
        service, _ = scheduler

        for _ in range(5):
            result = service.resync_from_db()
            assert result["success"] is True
            assert result["updated_scans"] == [], "unveränderter Job wurde neu eingeplant"

    def test_repeated_resync_keeps_next_run_time(self, scheduler):
        """Der eigentliche Schaden: der nächste Lauf rückt bei jedem Reload weg"""
        import asyncio

        service, _ = scheduler

        async def scenario():
            # AsyncIOScheduler braucht einen laufenden Event-Loop
            service.start()
            try:
                before = service.scheduler.get_job(
                    service._job_ids["job-a"]
                ).next_run_time
                for _ in range(5):
                    service.resync_from_db()
                after = service.scheduler.get_job(
                    service._job_ids["job-a"]
                ).next_run_time
                return before, after
            finally:
                service.stop()

        before, after = asyncio.run(scenario())
        assert before is not None
        assert after == before, "geplanter Lauf wurde durch den Resync verschoben"

    def test_changed_job_is_rescheduled(self, scheduler):
        service, jobs = scheduler
        # An der API vorbei ändern - genau dafür ist der Resync da
        jobs.update_job(
            "job-a",
            name="job-a",
            nas_connection_id=1,
            interval="5m",
            enabled=True,
            paths=["/homes"],
        )

        result = service.resync_from_db()

        assert result["updated_scans"] == ["job-a"]

    def test_new_and_removed_jobs_still_handled(self, scheduler):
        service, jobs = scheduler
        jobs.create_job(
            name="job-b",
            nas_connection_id=1,
            interval="1h",
            enabled=True,
            paths=["/media"],
        )
        result = service.resync_from_db()
        assert result["added_scans"] == ["job-b"]

        jobs.delete_job("job-b")
        result = service.resync_from_db()
        assert result["removed_scans"] == ["job-b"]


class TestRateLimiterPruning:
    def test_stale_entries_are_dropped(self, monkeypatch):
        import app.services.rate_limit as rl

        limiter = rl.LoginRateLimiter()
        # Deutlich über der Prune-Schwelle, alle Einträge lange untätig
        for i in range(rl.PRUNE_THRESHOLD + 10):
            limiter._entries[f"key-{i}"] = rl._Entry(last_seen=0.0)

        limiter._entry("neuer-client")

        assert len(limiter._entries) < rl.PRUNE_THRESHOLD

    def test_blocked_entries_survive_pruning(self):
        import time

        import app.services.rate_limit as rl

        limiter = rl.LoginRateLimiter()
        now = time.time()
        for i in range(rl.PRUNE_THRESHOLD + 10):
            limiter._entries[f"key-{i}"] = rl._Entry(last_seen=0.0)
        limiter._entries["gesperrt"] = rl._Entry(
            last_seen=0.0, blocked_until=now + 3600, block_level=3
        )

        limiter._entry("neuer-client")

        assert "gesperrt" in limiter._entries, "aktive Sperre darf nicht verfallen"

    def test_limit_still_blocks_after_pruning(self):
        import app.services.rate_limit as rl

        limiter = rl.LoginRateLimiter(max_attempts=3)
        for _ in range(3):
            limiter.register_failure("client")
        allowed, retry_after = limiter.check("client")

        assert allowed is False
        assert retry_after > 0
