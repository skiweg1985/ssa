"""Tests für die generischen Monitoring-Endpoints (/api/monitor*).

Kernpunkte:
- `severity` ist die einzige Achse, die ein Monitoring-System auswerten muss
- alle Felder sind IMMER vorhanden (null statt fehlend), damit JSONPath in
  Zabbix/Grafana zustandsunabhängig funktioniert
- ein laufender Scan verdeckt NIE das Ergebnis des vorherigen Laufs
- Teilfehler und Überfälligkeit sind ohne Zweit-Call sichtbar
- Konsistenz mit den PRTG-Endpoints (dieselbe Wahrheit, andere Darstellung)
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.jobs_store import initialize_jobs_store
from app.services.security import reset_key_cache

# Top-Level-Schlüssel des Job-Berichts - müssen alle immer vorhanden sein
SCAN_REPORT_KEYS = {
    "schema_version", "generated_at", "severity", "severity_text", "state",
    "reasons", "message", "scan", "run", "last_run", "last_success", "schedule",
}
RUN_KEYS = {"active", "started_at", "active_seconds", "progress_percent", "current_path"}
LAST_RUN_KEYS = {
    "at", "age_seconds", "status", "error", "duration_seconds",
    "folders_total", "folders_ok", "folders_failed", "folders_failed_names",
}
LAST_SUCCESS_KEYS = {
    "at", "age_seconds", "folders_ok", "total_bytes",
    "total_directories", "total_files",
}
SCHEDULE_KEYS = {
    "scheduled", "interval", "expected_interval_seconds", "next_run_at",
    "next_run_in_seconds", "overdue", "overdue_by_seconds",
    "stale_after_seconds", "overdue_after_seconds",
}
SEVERITY_TEXTS = {0: "ok", 1: "warning", 2: "critical"}


def assert_monitor_contract(body):
    """Prüft den Vertrag, der einen Feldzugriff erst verlässlich macht"""
    assert set(body.keys()) == SCAN_REPORT_KEYS
    assert set(body["run"].keys()) == RUN_KEYS
    assert set(body["last_run"].keys()) == LAST_RUN_KEYS
    assert set(body["last_success"].keys()) == LAST_SUCCESS_KEYS
    assert set(body["schedule"].keys()) == SCHEDULE_KEYS

    severity = body["severity"]
    assert isinstance(severity, int) and not isinstance(severity, bool)
    assert severity in (0, 1, 2), "UNKNOWN(3) darf nie geliefert werden"
    assert body["severity_text"] == SEVERITY_TEXTS[severity]
    assert isinstance(body["message"], str) and body["message"]
    if body["reasons"]:
        assert body["reasons"][0] == body["state"], (
            "reasons muss in Auswertungsreihenfolge stehen"
        )
    else:
        assert body["state"] == "ok"


# ----------------------------------------------------------------------
# Fixtures (bewusst je Testmodul dupliziert - das Repo hat kein conftest.py)
# ----------------------------------------------------------------------

def _reset_scanner_state():
    """
    Leert den Laufzeitzustand des Scanners vollständig.

    `scanner_service` ist ein Prozess-Singleton, und `_finish_scan` lässt
    absichtlich einen Grace-Period-Eintrag stehen (5 s, damit das Frontend den
    Abschluss mitbekommt). Ohne diesen Reset gilt ein Job in den Folgetests
    weiter als "laufend" - und "laufend" überschreibt im PRTG-Sensor jeden
    anderen Status.
    """
    from app.services.scanner import scanner_service

    with scanner_service._state_lock:
        scanner_service._running_scans.clear()
        scanner_service._scan_status.clear()
        scanner_service._scan_finished_at.clear()


@pytest.fixture(autouse=True)
def clean_scanner_state():
    """Macht die Suite unabhängig von der Testreihenfolge"""
    _reset_scanner_state()
    yield
    _reset_scanner_state()


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
def api_token_headers(client, auth_headers):
    response = client.post(
        "/api/api-tokens", headers=auth_headers, json={"name": "Monitoring"}
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _result(slug, name, timestamp=None, status="completed", folders=None, error=None):
    """Ein Scan-Ergebnis; folders ist eine Liste (name, bytes, success)"""
    if folders is None:
        folders = [("/design", 1073741824, True), ("/photo", 500000000, True)]
    return ScanResult(
        scan_slug=slug,
        scan_name=name,
        timestamp=timestamp or datetime.now(timezone.utc),
        status=status,
        error=error,
        results=[
            ScanResultItem(
                folder_name=folder,
                success=success,
                num_dir=10 if success else None,
                num_file=100 if success else None,
                total_size=(
                    TotalSize(bytes=size, formatted=1.0, unit="GB") if success else None
                ),
                elapsed_time_ms=12530 if success else None,
                error=None if success else "Ordner nicht erreichbar",
            )
            for folder, size, success in folders
        ],
    )


def _add_result(job, **kwargs):
    import app.services.storage as storage_module

    storage_module._storage_instance.add_result(
        job["slug"],
        job["name"],
        _result(job["slug"], job["name"], **kwargs),
        "nas.local",
    )


def _create_job(client, auth_headers, name, paths, interval="6h", enabled=True):
    connection = client.post(
        "/api/nas-connections",
        headers=auth_headers,
        json={
            "name": f"NAS-{name}",
            "host": "nas.local",
            "username": "u",
            "password": "p",
        },
    ).json()
    return client.post(
        "/api/scan-jobs",
        headers=auth_headers,
        json={
            "name": name,
            "nas_connection_id": connection["id"],
            "paths": paths,
            "interval": interval,
            "enabled": enabled,
        },
    ).json()


@pytest.fixture
def seeded_job(client, auth_headers):
    """Job mit zwei Pfaden und einem erfolgreichen Lauf"""
    job = _create_job(client, auth_headers, "Design Scan", ["/design", "/photo"])
    _add_result(job)
    return job


def _get(client, headers, job, **params):
    return client.get(
        f"/api/monitor/scans/{job['slug']}", headers=headers, params=params
    )


# ----------------------------------------------------------------------
# Vertrag und Grundzustand
# ----------------------------------------------------------------------

class TestScanContract:
    def test_ok_report_satisfies_contract(self, client, auth_headers, seeded_job):
        response = _get(client, auth_headers, seeded_job)
        assert response.status_code == 200
        body = response.json()
        assert_monitor_contract(body)
        assert body["schema_version"] == "ssa.monitor.scan/1"
        assert body["severity"] == 0
        assert body["state"] == "ok"
        assert body["reasons"] == []
        assert body["scan"] == {
            "slug": "design-scan",
            "name": "Design Scan",
            "enabled": True,
        }

    def test_measurements_come_from_last_success(self, client, auth_headers, seeded_job):
        body = _get(client, auth_headers, seeded_job).json()
        assert body["last_success"]["total_bytes"] == 1073741824 + 500000000
        assert body["last_success"]["total_directories"] == 20
        assert body["last_success"]["total_files"] == 200
        assert body["last_success"]["folders_ok"] == 2

    def test_severity_headers_always_present(self, client, auth_headers, seeded_job):
        response = _get(client, auth_headers, seeded_job)
        assert response.headers["X-SSA-Severity"] == "0"
        assert response.headers["X-SSA-State"] == "ok"

    def test_no_management_data_leaks(self, client, auth_headers, seeded_job):
        """Verwaltungsdaten gehören nach /api/scans, nicht in den Bericht"""
        body = _get(client, auth_headers, seeded_job).json()
        assert set(body["scan"].keys()) == {"slug", "name", "enabled"}
        assert "nas" not in body
        assert "paths" not in body


# ----------------------------------------------------------------------
# Zustände
# ----------------------------------------------------------------------

class TestScanStates:
    def test_partial_failure_is_warning(self, client, auth_headers):
        job = _create_job(client, auth_headers, "Teil", ["/a", "/b", "/c"])
        _add_result(
            job,
            folders=[("/a", 100, True), ("/b", 200, True), ("/c", 0, False)],
        )
        body = _get(client, auth_headers, job).json()
        assert_monitor_contract(body)
        assert body["severity"] == 1
        assert body["state"] == "partial"
        assert body["last_run"]["status"] == "completed", (
            "der rohe Lauf-Status bleibt 'completed' - genau darum ist er als "
            "Alarmkriterium untauglich"
        )
        assert body["last_run"]["folders_total"] == 3
        assert body["last_run"]["folders_ok"] == 2
        assert body["last_run"]["folders_failed"] == 1
        assert body["last_run"]["folders_failed_names"] == ["/c"]
        assert "/c" in body["message"]

    def test_failed_run_keeps_last_success(self, client, auth_headers, seeded_job):
        """Der Kern der Ablösung: Fehler UND letzte gute Daten gleichzeitig"""
        _add_result(
            seeded_job, status="failed", folders=[], error="Login fehlgeschlagen"
        )
        body = _get(client, auth_headers, seeded_job).json()
        assert_monitor_contract(body)
        assert body["severity"] == 2
        assert body["state"] == "failed"
        assert body["last_run"]["error"] == "Login fehlgeschlagen"
        assert "Login fehlgeschlagen" in body["message"]
        assert body["last_success"]["at"] is not None
        assert body["last_success"]["total_bytes"] == 1073741824 + 500000000

    def test_running_scan_does_not_hide_previous_result(
        self, client, auth_headers, seeded_job
    ):
        """Ein laufender Scan ist eine eigene Achse, kein Status"""
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        try:
            body = _get(client, auth_headers, seeded_job).json()
        finally:
            _reset_scanner_state()

        assert body["run"]["active"] is True
        assert body["state"] == "ok", "der laufende Scan darf den state nicht ersetzen"
        assert body["severity"] == 0
        assert body["last_run"]["status"] == "completed"
        assert body["last_run"]["at"] is not None
        assert body["schedule"]["overdue"] is False

    def test_running_scan_suspends_overdue(self, client, auth_headers):
        """Wer gerade läuft, ist nicht überfällig"""
        from app.services.scanner import scanner_service

        job = _create_job(client, auth_headers, "Laeuft", ["/x"])
        _add_result(
            job, timestamp=datetime.now(timezone.utc) - timedelta(hours=30)
        )
        assert scanner_service._try_start_scan(job["slug"]) is True
        try:
            body = _get(client, auth_headers, job).json()
        finally:
            _reset_scanner_state()

        assert body["run"]["active"] is True
        assert body["schedule"]["overdue"] is False
        assert body["state"] != "overdue"

    def test_never_run_is_warning_not_error_response(self, client, auth_headers):
        """HTTP 200 mit Daten - anders als der PRTG-Endpoint (prtg.error)"""
        job = _create_job(client, auth_headers, "Frisch", ["/neu"])
        response = _get(client, auth_headers, job)
        assert response.status_code == 200
        body = response.json()
        assert_monitor_contract(body)
        assert body["severity"] == 1
        assert body["state"] == "never_run"
        assert body["last_run"]["at"] is None
        assert body["last_run"]["status"] is None
        assert body["last_success"]["at"] is None
        assert body["last_success"]["total_bytes"] is None

    def test_disabled_job_never_alarms(self, client, auth_headers, seeded_job):
        """Deaktiviert überstimmt einen Fehllauf - sonst alarmiert Absicht"""
        _add_result(seeded_job, status="failed", folders=[], error="egal")
        client.put(
            f"/api/scan-jobs/{seeded_job['slug']}",
            headers=auth_headers,
            json={
                "name": seeded_job["name"],
                "nas_connection_id": seeded_job["nas_connection_id"],
                "paths": seeded_job["paths"],
                "interval": seeded_job["interval"],
                "enabled": False,
            },
        )
        body = _get(client, auth_headers, seeded_job).json()
        assert_monitor_contract(body)
        assert body["severity"] == 0
        assert body["state"] == "disabled"
        assert "failed" in body["reasons"], (
            "der Fehllauf bleibt als Grund sichtbar, alarmiert aber nicht"
        )
        assert body["scan"]["enabled"] is False
        assert body["schedule"]["scheduled"] is False
        assert body["schedule"]["expected_interval_seconds"] is None
        assert body["schedule"]["stale_after_seconds"] is None
        assert body["schedule"]["overdue_after_seconds"] is None
        assert body["schedule"]["overdue"] is False

    def test_overdue_is_computed_server_side(self, client, auth_headers):
        """Kein Cron-Parsing im Client: der Server rechnet die Schwellwerte"""
        job = _create_job(client, auth_headers, "Alt", ["/alt"], interval="6h")
        _add_result(job, timestamp=datetime.now(timezone.utc) - timedelta(hours=30))
        body = _get(client, auth_headers, job).json()
        assert_monitor_contract(body)
        assert body["severity"] == 2
        assert body["state"] == "overdue"
        assert body["reasons"] == ["overdue", "stale"]
        # 6h Intervall -> Warnung ab 2x, kritisch ab 3x (wie die PRTG-Limits)
        assert body["schedule"]["stale_after_seconds"] == pytest.approx(6 * 3600 * 2)
        assert body["schedule"]["overdue_after_seconds"] == pytest.approx(6 * 3600 * 3)
        assert body["schedule"]["overdue"] is True
        assert body["schedule"]["overdue_by_seconds"] > 0
        assert body["last_run"]["age_seconds"] == pytest.approx(30 * 3600, rel=0.01)

    def test_stale_is_only_a_warning(self, client, auth_headers):
        """Zwischen 2x und 3x Intervall: Warnung, noch nicht kritisch"""
        job = _create_job(client, auth_headers, "Lauwarm", ["/l"], interval="6h")
        _add_result(job, timestamp=datetime.now(timezone.utc) - timedelta(hours=14))
        body = _get(client, auth_headers, job).json()
        assert body["severity"] == 1
        assert body["state"] == "stale"
        assert body["schedule"]["overdue"] is False
        assert body["schedule"]["overdue_by_seconds"] == 0

    def test_naive_timestamp_does_not_crash(self, client, auth_headers, seeded_job):
        """Regression: alte Datensätze können naive Timestamps enthalten"""
        _add_result(seeded_job, timestamp=datetime.utcnow())
        response = _get(client, auth_headers, seeded_job)
        assert response.status_code == 200
        assert_monitor_contract(response.json())

    def test_schedule_distinguishes_the_null_cases(
        self, client, auth_headers, seeded_job
    ):
        """`scheduled` löst die Mehrdeutigkeit des alten `next_run: null` auf"""
        body = _get(client, auth_headers, seeded_job).json()
        assert body["schedule"]["scheduled"] is True
        assert body["schedule"]["next_run_at"] is not None
        assert body["schedule"]["interval"] == "6h"
        assert body["schedule"]["expected_interval_seconds"] == pytest.approx(21600)


# ----------------------------------------------------------------------
# HTTP-Status, Header und Auth
# ----------------------------------------------------------------------

class TestHttpAndAuth:
    def test_unknown_slug_is_404(self, client, auth_headers):
        response = client.get("/api/monitor/scans/gibtsnicht", headers=auth_headers)
        assert response.status_code == 404
        assert "gibtsnicht" in response.json()["detail"]

    def test_requires_authentication(self, client, seeded_job):
        for path in (
            "/api/monitor",
            "/api/monitor/scans",
            "/api/monitor/server",
            "/api/monitor/scans/design-scan",
        ):
            assert client.get(path).status_code == 401, path

    def test_monitoring_token_may_read_all_reports(
        self, client, api_token_headers, seeded_job
    ):
        """Sichert den Eintrag in API_TOKEN_ALLOWED_PREFIXES ab"""
        for path in (
            "/api/monitor",
            "/api/monitor/scans",
            "/api/monitor/server",
            "/api/monitor/scans/design-scan",
        ):
            assert client.get(path, headers=api_token_headers).status_code == 200, path

    def test_monitoring_token_still_barred_from_management(
        self, client, api_token_headers
    ):
        assert client.get("/api/api-tokens", headers=api_token_headers).status_code == 403
        assert (
            client.post(
                "/api/scans/design-scan/trigger", headers=api_token_headers
            ).status_code
            == 403
        )

    def test_default_is_always_http_200(self, client, auth_headers, seeded_job):
        """Ohne Opt-in bleibt der Statuscode 200 - der Body trägt die Aussage"""
        _add_result(seeded_job, status="failed", folders=[], error="kaputt")
        response = _get(client, auth_headers, seeded_job)
        assert response.status_code == 200
        assert response.json()["severity"] == 2
        assert response.headers["X-SSA-Severity"] == "2"
        assert response.headers["X-SSA-State"] == "failed"

    def test_http_status_opt_in_maps_critical_to_503(
        self, client, auth_headers, seeded_job
    ):
        _add_result(seeded_job, status="failed", folders=[], error="kaputt")
        response = _get(client, auth_headers, seeded_job, http_status=1)
        assert response.status_code == 503
        assert response.json()["severity"] == 2
        assert response.headers["X-SSA-Severity"] == "2"

    def test_http_status_opt_in_keeps_200_when_healthy(
        self, client, auth_headers, seeded_job
    ):
        response = _get(client, auth_headers, seeded_job, http_status=1)
        assert response.status_code == 200

    def test_http_status_opt_in_keeps_200_on_warning(self, client, auth_headers):
        """Nur kritisch wird 503 - Warnungen bleiben erreichbar"""
        job = _create_job(client, auth_headers, "Warn", ["/w"])
        response = _get(client, auth_headers, job, http_status=1)
        assert response.json()["severity"] == 1
        assert response.status_code == 200


# ----------------------------------------------------------------------
# Roll-up über alle Jobs
# ----------------------------------------------------------------------

class TestScansRollup:
    def test_severity_is_maximum_over_jobs(self, client, auth_headers, seeded_job):
        broken = _create_job(client, auth_headers, "Kaputt", ["/k"])
        _add_result(broken, status="failed", folders=[], error="Timeout")

        body = client.get("/api/monitor/scans", headers=auth_headers).json()
        assert body["schema_version"] == "ssa.monitor.scans/1"
        assert body["severity"] == 2
        assert body["state"] == "failed"
        assert body["summary"]["total"] == 2
        assert body["summary"]["critical"] == 1
        assert body["summary"]["ok"] == 1
        assert body["summary"]["failed"] == 1
        assert body["summary"]["worst_slug"] == broken["slug"]

    def test_problems_lists_only_the_notable_jobs(
        self, client, auth_headers, seeded_job
    ):
        broken = _create_job(client, auth_headers, "Kaputt", ["/k"])
        _add_result(broken, status="failed", folders=[], error="Timeout")

        body = client.get("/api/monitor/scans", headers=auth_headers).json()
        slugs = [problem["slug"] for problem in body["problems"]]
        assert slugs == [broken["slug"]], "gesunde Jobs gehören nicht in problems"
        assert body["problems"][0]["severity"] == 2
        assert body["problems"][0]["state"] == "failed"
        assert "Timeout" in body["problems"][0]["message"]

    def test_problems_sorted_worst_first(self, client, auth_headers, seeded_job):
        warn = _create_job(client, auth_headers, "Warnung", ["/w"])  # never_run -> 1
        crit = _create_job(client, auth_headers, "Kritisch", ["/c"])
        _add_result(crit, status="failed", folders=[], error="hin")

        body = client.get("/api/monitor/scans", headers=auth_headers).json()
        severities = [problem["severity"] for problem in body["problems"]]
        assert severities == sorted(severities, reverse=True)
        assert body["problems"][0]["slug"] == crit["slug"]
        assert warn["slug"] in [problem["slug"] for problem in body["problems"]]

    def test_include_scans_false_keeps_summary_and_problems(
        self, client, auth_headers, seeded_job
    ):
        body = client.get(
            "/api/monitor/scans", headers=auth_headers, params={"include_scans": 0}
        ).json()
        assert body["scans"] is None
        assert body["summary"]["total"] == 1
        assert "problems" in body

    def test_scans_contains_full_reports(self, client, auth_headers, seeded_job):
        body = client.get("/api/monitor/scans", headers=auth_headers).json()
        assert len(body["scans"]) == 1
        assert_monitor_contract(body["scans"][0])

    def test_disabled_job_does_not_raise_rollup_severity(self, client, auth_headers):
        job = _create_job(client, auth_headers, "Aus", ["/aus"], enabled=False)
        _add_result(job, status="failed", folders=[], error="egal")

        body = client.get("/api/monitor/scans", headers=auth_headers).json()
        assert body["severity"] == 0
        assert body["summary"]["disabled"] == 1
        assert body["summary"]["enabled"] == 0
        assert body["problems"] == []

    def test_empty_instance_is_ok(self, client, auth_headers):
        body = client.get("/api/monitor/scans", headers=auth_headers).json()
        assert body["severity"] == 0
        assert body["summary"]["total"] == 0
        assert "Keine Scan-Jobs" in body["message"]

    def test_stalest_tracks_the_oldest_enabled_job(self, client, auth_headers):
        fresh = _create_job(client, auth_headers, "Frisch", ["/f"])
        _add_result(fresh)
        old = _create_job(client, auth_headers, "Alt", ["/a"])
        _add_result(old, timestamp=datetime.now(timezone.utc) - timedelta(hours=30))

        summary = client.get("/api/monitor/scans", headers=auth_headers).json()["summary"]
        assert summary["stalest_slug"] == old["slug"]
        assert summary["stalest_age_seconds"] == pytest.approx(30 * 3600, rel=0.01)


# ----------------------------------------------------------------------
# Instanz- und Server-Bericht
# ----------------------------------------------------------------------

class TestInstanceAndServer:
    def test_instance_combines_both_components(self, client, auth_headers, seeded_job):
        body = client.get("/api/monitor", headers=auth_headers).json()
        assert body["schema_version"] == "ssa.monitor.instance/1"
        assert set(body["components"].keys()) == {"server", "scans"}
        assert body["severity"] == max(
            body["components"]["server"]["severity"],
            body["components"]["scans"]["severity"],
        )
        assert body["severity"] == 0

    def test_instance_severity_follows_worst_component(
        self, client, auth_headers, seeded_job
    ):
        _add_result(seeded_job, status="failed", folders=[], error="hin")
        body = client.get("/api/monitor", headers=auth_headers).json()
        assert body["components"]["scans"]["severity"] == 2
        assert body["severity"] == 2
        assert body["state"] == "failed"
        assert body["problems"][0]["slug"] == seeded_job["slug"]

    def test_server_report_is_healthy_by_default(self, client, auth_headers):
        response = client.get("/api/monitor/server", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "ssa.monitor.server/1"
        assert body["severity"] == 0
        assert body["state"] == "ok"
        assert body["scheduler"]["running"] is True
        assert response.headers["X-SSA-State"] == "ok"

    def test_stopped_scheduler_is_critical(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(
            "app.services.health.collect_scheduler_metrics",
            lambda: {"running": False, "total_jobs": 0, "enabled_jobs": 0},
        )
        body = client.get("/api/monitor/server", headers=auth_headers).json()
        assert body["severity"] == 2
        assert body["state"] == "scheduler_down"
        assert body["scheduler"]["running"] is False

    def test_without_psutil_values_are_null_not_zero(
        self, client, auth_headers, monkeypatch
    ):
        """0 % Disk belegt wäre eine gefährliche Fehldeutung"""
        monkeypatch.setattr("app.services.health.PSUTIL_AVAILABLE", False)
        body = client.get("/api/monitor/server", headers=auth_headers).json()
        assert body["system"]["available"] is False
        assert body["system"]["disk_percent"] is None
        assert body["system"]["memory_percent"] is None
        assert body["system"]["cpu_percent"] is None
        assert body["severity"] == 0, "fehlendes psutil ist kein Alarm"

    def test_failed_jobs_do_not_raise_server_severity(
        self, client, auth_headers, seeded_job
    ):
        """Sonst alarmieren Server- und Scans-Check für dieselbe Ursache"""
        _add_result(seeded_job, status="failed", folders=[], error="hin")
        body = client.get("/api/monitor/server", headers=auth_headers).json()
        assert body["jobs"]["failed"] == 1
        assert body["severity"] == 0
        assert body["state"] == "ok"


# ----------------------------------------------------------------------
# Ablösung des alten Status-Endpoints
# ----------------------------------------------------------------------

class TestDeprecatedStatusEndpoint:
    def test_signals_deprecation_and_successor(self, client, auth_headers, seeded_job):
        response = client.get(
            f"/api/scans/{seeded_job['slug']}/status", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
        assert 'rel="successor-version"' in response.headers["Link"]
        assert f"/api/monitor/scans/{seeded_job['slug']}" in response.headers["Link"]
        assert "Sunset" not in response.headers, (
            "kein Entfernungsdatum - der Endpoint bleibt erhalten"
        )

    def test_schema_unchanged(self, client, auth_headers, seeded_job):
        """Rückwärtskompatibilität: bestehende Clients dürfen nicht brechen"""
        body = client.get(
            f"/api/scans/{seeded_job['slug']}/status", headers=auth_headers
        ).json()
        for key in ("scan_slug", "scan_name", "status", "last_run", "next_run", "enabled"):
            assert key in body, f"Feld '{key}' fehlt - das wäre ein Breaking Change"
        assert body["status"] == "completed"

    def test_marked_deprecated_in_openapi(self, client, auth_headers):
        schema = client.get("/openapi.json").json()
        old = schema["paths"]["/api/scans/{scan_identifier}/status"]["get"]
        assert old.get("deprecated") is True
        new = schema["paths"]["/api/monitor/scans/{scan_identifier}"]["get"]
        assert new.get("deprecated") is not True

    def test_new_endpoint_answers_what_the_old_one_could_not(
        self, client, auth_headers, seeded_job
    ):
        """Der eigentliche Grund für die Ablösung, an einem Fall belegt"""
        _add_result(seeded_job, status="failed", folders=[], error="NAS offline")

        old = client.get(
            f"/api/scans/{seeded_job['slug']}/status", headers=auth_headers
        ).json()
        new = _get(client, auth_headers, seeded_job).json()

        # Alt: kein Fehlertext, kein Zeitstempel des letzten Erfolgs,
        # kein Schweregrad - "failed" ist alles, was der Client bekommt.
        assert old["status"] == "failed"
        assert "error" not in old
        assert "last_success" not in old
        assert "severity" not in old

        # Neu: alles in einer Antwort.
        assert new["severity"] == 2
        assert new["last_run"]["error"] == "NAS offline"
        assert new["last_success"]["at"] is not None
        assert new["last_success"]["total_bytes"] > 0


# ----------------------------------------------------------------------
# Konsistenz mit den PRTG-Endpoints
# ----------------------------------------------------------------------

class TestPrtgConsistency:
    def _prtg_channels(self, client, headers, slug):
        body = client.get(f"/api/prtg/scans/{slug}", headers=headers).json()
        return {channel["channel"]: channel for channel in body["prtg"].get("result", [])}

    def test_ok_maps_to_prtg_status_0(self, client, auth_headers, seeded_job):
        monitor = _get(client, auth_headers, seeded_job).json()
        channels = self._prtg_channels(client, auth_headers, seeded_job["slug"])
        assert monitor["state"] == "ok"
        assert channels["Status"]["value"] == "0"

    def test_failed_maps_to_prtg_status_4(self, client, auth_headers, seeded_job):
        _add_result(seeded_job, status="failed", folders=[], error="hin")
        monitor = _get(client, auth_headers, seeded_job).json()
        channels = self._prtg_channels(client, auth_headers, seeded_job["slug"])
        assert monitor["state"] == "failed" and monitor["severity"] == 2
        assert channels["Status"]["value"] == "4"

    def test_disabled_diverges_on_purpose(self, client, auth_headers, seeded_job):
        """PRTG-Status 2 (alarmiert) vs. generisch severity 0 (alarmiert nicht)"""
        client.put(
            f"/api/scan-jobs/{seeded_job['slug']}",
            headers=auth_headers,
            json={
                "name": seeded_job["name"],
                "nas_connection_id": seeded_job["nas_connection_id"],
                "paths": seeded_job["paths"],
                "interval": seeded_job["interval"],
                "enabled": False,
            },
        )
        monitor = _get(client, auth_headers, seeded_job).json()
        channels = self._prtg_channels(client, auth_headers, seeded_job["slug"])
        assert channels["Status"]["value"] == "2"
        assert monitor["state"] == "disabled"
        assert monitor["severity"] == 0

    def test_running_diverges_on_purpose(self, client, auth_headers, seeded_job):
        """PRTG überschreibt mit Status 1, generisch bleibt der Vorlauf sichtbar"""
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        try:
            monitor = _get(client, auth_headers, seeded_job).json()
            channels = self._prtg_channels(client, auth_headers, seeded_job["slug"])
        finally:
            _reset_scanner_state()

        assert channels["Status"]["value"] == "1"
        assert monitor["run"]["active"] is True
        assert monitor["state"] == "ok"

    def test_shared_age_and_folder_numbers(self, client, auth_headers, seeded_job):
        """Beide Endpoints müssen dieselbe Wahrheit berichten"""
        monitor = _get(client, auth_headers, seeded_job).json()
        channels = self._prtg_channels(client, auth_headers, seeded_job["slug"])
        assert int(channels["Ordner Fehler"]["value"]) == monitor["last_run"][
            "folders_failed"
        ]
        assert int(channels["Ordner OK"]["value"]) == monitor["last_run"]["folders_ok"]
        assert float(channels["Alter letzter Lauf"]["value"]) == pytest.approx(
            monitor["last_run"]["age_seconds"], abs=5
        )
        assert int(channels["Gesamtgröße"]["value"]) == monitor["last_success"][
            "total_bytes"
        ]

    def test_age_thresholds_match_prtg_limits(self, client, auth_headers, seeded_job):
        """`overdue_after_seconds` == PRTG-Error-Limit des Alters-Kanals"""
        monitor = _get(client, auth_headers, seeded_job).json()
        channels = self._prtg_channels(client, auth_headers, seeded_job["slug"])
        age_channel = channels["Alter letzter Lauf"]
        assert float(age_channel["limitmaxwarning"]) == pytest.approx(
            monitor["schedule"]["stale_after_seconds"]
        )
        assert float(age_channel["limitmaxerror"]) == pytest.approx(
            monitor["schedule"]["overdue_after_seconds"]
        )
