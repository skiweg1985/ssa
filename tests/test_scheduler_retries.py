"""Retry-Verhalten geplanter Scan-Jobs."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.config import NASConfigYAML, ScanTaskConfigYAML
from app.models.scan import ScanResult, ScanResultItem
from app.services.scheduler import SchedulerService, get_scan_retry_policy


def _config() -> ScanTaskConfigYAML:
    return ScanTaskConfigYAML(
        name="Retry Scan",
        slug="retry-scan",
        nas=NASConfigYAML(
            host="nas.example.test",
            username="scanner",
            password="secret",
        ),
        paths=["/data"],
        interval="6h",
        enabled=True,
    )


def _result(status: str, *, partial: bool = False) -> ScanResult:
    return ScanResult(
        scan_slug="retry-scan",
        scan_name="Retry Scan",
        timestamp=datetime.now(timezone.utc),
        status=status,
        results=[
            ScanResultItem(
                folder_name="/data",
                success=not partial,
                error="Pfad nicht erreichbar" if partial else None,
            )
        ],
        error="NAS nicht erreichbar" if status == "failed" else None,
    )


class _Jobs:
    def __init__(self, config: ScanTaskConfigYAML):
        self.config = config
        self.job = {"slug": config.slug, "enabled": True}

    def get_job(self, _slug):
        return self.job

    def to_scan_config(self, _job):
        return self.config


class _Storage:
    latest = None

    def get_latest_result(self, _slug):
        return self.latest


def _run_sequence(
    monkeypatch,
    results,
    *,
    count=2,
    next_regular=None,
    job_enabled=True,
    job_present=True,
):
    import app.services.jobs_store as jobs_module
    import app.services.storage as storage_module
    from app.services import scheduler as scheduler_module

    config = _config()
    jobs = _Jobs(config)
    jobs.job = (
        {"slug": config.slug, "enabled": job_enabled}
        if job_present
        else None
    )
    stored = _Storage()
    monkeypatch.setattr(jobs_module, "get_jobs_store", lambda: jobs)
    monkeypatch.setattr(storage_module, "get_storage", lambda: stored)
    monkeypatch.setenv("SSA_SCAN_RETRY_COUNT", str(count))
    monkeypatch.setenv("SSA_SCAN_RETRY_DELAY_SECONDS", "10")
    monkeypatch.setattr(scheduler_module.random, "randint", lambda _a, _b: 0)

    service = SchedulerService()
    monkeypatch.setattr(service, "_next_regular_run", lambda _slug: next_regular)
    monkeypatch.setattr(
        service,
        "_wait_for_retry",
        AsyncMock(return_value=False),
    )
    run_scan = AsyncMock(side_effect=results)
    monkeypatch.setattr(scheduler_module.scanner_service, "run_scan", run_scan)
    monkeypatch.setattr(
        scheduler_module.scanner_service, "is_scan_running", lambda _slug: False
    )

    asyncio.run(service._run_scan_job(config))
    return service, run_scan, jobs, stored


@pytest.mark.parametrize(
    "first",
    [
        _result("failed"),
        _result("completed", partial=True),
    ],
)
def test_failed_and_partial_scheduled_runs_are_retried(monkeypatch, first):
    service, run_scan, _jobs, _stored = _run_sequence(
        monkeypatch, [first, _result("completed")]
    )

    assert run_scan.await_count == 2
    assert service.get_retry_info("retry-scan").state is None


def test_retry_limit_means_two_additional_attempts(monkeypatch):
    _service, run_scan, _jobs, _stored = _run_sequence(
        monkeypatch,
        [_result("failed"), _result("failed"), _result("failed")],
    )

    assert run_scan.await_count == 3


@pytest.mark.parametrize("status", ["completed", "cancelled", "running"])
def test_non_failure_status_is_not_retried(monkeypatch, status):
    _service, run_scan, _jobs, _stored = _run_sequence(
        monkeypatch, [_result(status)]
    )

    assert run_scan.await_count == 1


def test_retry_count_zero_disables_retries(monkeypatch):
    _service, run_scan, _jobs, _stored = _run_sequence(
        monkeypatch, [_result("failed")], count=0
    )

    assert run_scan.await_count == 1


def test_regular_run_due_before_retry_wins(monkeypatch):
    next_regular = datetime.now(timezone.utc) + timedelta(seconds=5)
    _service, run_scan, _jobs, _stored = _run_sequence(
        monkeypatch, [_result("failed")], next_regular=next_regular
    )

    assert run_scan.await_count == 1


@pytest.mark.parametrize(
    ("job_enabled", "job_present"),
    [(False, True), (True, False)],
)
def test_deleted_or_disabled_job_is_not_retried(
    monkeypatch, job_enabled, job_present
):
    _service, run_scan, _jobs, _stored = _run_sequence(
        monkeypatch,
        [_result("failed")],
        job_enabled=job_enabled,
        job_present=job_present,
    )

    assert run_scan.await_count == 1


def test_pending_retry_is_visible_and_can_be_cancelled(monkeypatch):
    import app.services.jobs_store as jobs_module
    import app.services.storage as storage_module
    from app.services import scheduler as scheduler_module

    async def scenario():
        config = _config()
        jobs = _Jobs(config)
        monkeypatch.setattr(jobs_module, "get_jobs_store", lambda: jobs)
        monkeypatch.setattr(storage_module, "get_storage", lambda: _Storage())
        monkeypatch.setenv("SSA_SCAN_RETRY_COUNT", "2")
        monkeypatch.setenv("SSA_SCAN_RETRY_DELAY_SECONDS", "10")
        monkeypatch.setattr(scheduler_module.random, "randint", lambda _a, _b: 0)
        monkeypatch.setattr(
            scheduler_module.scanner_service,
            "run_scan",
            AsyncMock(return_value=_result("failed")),
        )

        service = SchedulerService()
        task = asyncio.create_task(service._run_scan_job(config))
        for _ in range(100):
            info = service.get_retry_info(config.slug)
            if info.state == "pending":
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("Retry wurde nicht als pending sichtbar")

        assert info.attempt == 1
        assert info.max_attempts == 2
        assert info.reason == "failed"
        assert info.scheduled_at is not None
        assert service.cancel_retry_sequence(config.slug, "Testabbruch") is True
        await task
        assert service.get_retry_info(config.slug).state is None

    asyncio.run(scenario())


def test_manual_trigger_supersedes_pending_retry(monkeypatch):
    import app.services.jobs_store as jobs_module
    from app.api import routes
    from fastapi import BackgroundTasks

    config = _config()
    jobs = _Jobs(config)
    monkeypatch.setattr(jobs_module, "get_jobs_store", lambda: jobs)
    monkeypatch.setattr(routes.scanner_service, "is_scan_running", lambda _slug: False)
    monkeypatch.setattr(routes.scanner_service, "run_scan", AsyncMock())

    # Die Scheduler-Methode ist synchron; AsyncMock eignet sich hier nicht.
    cancelled = []
    monkeypatch.setattr(
        routes.scheduler_service,
        "cancel_retry_sequence",
        lambda slug, reason: cancelled.append((slug, reason)) or True,
    )
    background_tasks = BackgroundTasks()

    response = asyncio.run(routes.trigger_scan(config.slug, background_tasks))

    assert response.triggered is True
    assert cancelled == [(config.slug, "manueller Lauf gestartet")]
    assert len(background_tasks.tasks) == 1


@pytest.mark.parametrize(
    ("count", "delay", "expected"),
    [
        ("0", "10", (0, 10)),
        ("10", "86400", (10, 86400)),
        ("11", "9", (2, 300)),
        ("ungueltig", "ungueltig", (2, 300)),
    ],
)
def test_retry_environment_is_validated(monkeypatch, count, delay, expected):
    monkeypatch.setenv("SSA_SCAN_RETRY_COUNT", count)
    monkeypatch.setenv("SSA_SCAN_RETRY_DELAY_SECONDS", delay)

    policy = get_scan_retry_policy()

    assert (policy.count, policy.delay_seconds) == expected
