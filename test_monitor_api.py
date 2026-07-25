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
RUN_KEYS = {
    "active", "started_at", "active_seconds", "progress_percent", "current_path",
    "stuck_after_seconds", "stuck", "cancel_requested",
}
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

    def test_running_scan_reports_start_time_and_threshold(
        self, client, auth_headers, seeded_job
    ):
        """Laufzeit und Hängen-Schwelle sind sichtbar, solange der Scan läuft"""
        from app.services.scanner import PATH_MAX_WAIT_SECONDS, scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        try:
            body = _get(client, auth_headers, seeded_job).json()
        finally:
            _reset_scanner_state()

        assert body["run"]["active"] is True
        assert body["run"]["started_at"] is not None
        assert body["run"]["active_seconds"] is not None
        assert body["run"]["active_seconds"] >= 0
        assert body["run"]["stuck"] is False
        assert body["run"]["cancel_requested"] is False
        # 2 Pfade -> 2 * 300 * 2 = 1200, unter der Untergrenze von 1800
        assert body["run"]["stuck_after_seconds"] == pytest.approx(
            max(1800, 2 * PATH_MAX_WAIT_SECONDS * 2)
        )

    def test_long_running_scan_is_stuck_and_critical(
        self, client, auth_headers, seeded_job
    ):
        """Der eigentliche Zweck: ein hängender Lauf darf nicht unsichtbar bleiben"""
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        # Startzeitpunkt künstlich zurückdatieren
        with scanner_service._state_lock:
            scanner_service._scan_started_at[seeded_job["slug"]] = datetime.now(
                timezone.utc
            ) - timedelta(hours=5)
        try:
            body = _get(client, auth_headers, seeded_job).json()
        finally:
            _reset_scanner_state()

        assert_monitor_contract(body)
        assert body["run"]["active"] is True
        assert body["run"]["stuck"] is True
        assert body["severity"] == 2
        assert body["state"] == "stuck"
        assert "hängt" in body["message"]
        assert "cancel" in body["message"], (
            "die Meldung soll den Weg zum Abbruch nennen"
        )

    def test_stuck_beats_a_failed_previous_run(self, client, auth_headers, seeded_job):
        """Der akute Zustand gewinnt gegen das Ergebnis eines alten Laufs"""
        from app.services.scanner import scanner_service

        _add_result(seeded_job, status="failed", folders=[], error="alter Fehler")
        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        with scanner_service._state_lock:
            scanner_service._scan_started_at[seeded_job["slug"]] = datetime.now(
                timezone.utc
            ) - timedelta(hours=5)
        try:
            body = _get(client, auth_headers, seeded_job).json()
        finally:
            _reset_scanner_state()

        assert body["state"] == "stuck"
        assert body["reasons"][0] == "stuck"
        assert "failed" in body["reasons"], "der alte Fehllauf bleibt als Grund sichtbar"

    def test_disabled_job_is_never_stuck(self, client, auth_headers, seeded_job):
        """Auch ein hängender Lauf alarmiert nicht, wenn der Job deaktiviert ist"""
        from app.services.scanner import scanner_service

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
        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        with scanner_service._state_lock:
            scanner_service._scan_started_at[seeded_job["slug"]] = datetime.now(
                timezone.utc
            ) - timedelta(hours=5)
        try:
            body = _get(client, auth_headers, seeded_job).json()
        finally:
            _reset_scanner_state()

        assert body["state"] == "disabled"
        assert body["severity"] == 0
        assert "stuck" in body["reasons"]

    def test_cancelled_run_is_warning_not_failure(self, client, auth_headers, seeded_job):
        """Ein Abbruch ist kein Fehler - Warnung statt kritisch"""
        _add_result(
            seeded_job,
            status="cancelled",
            folders=[],
            error="Abgebrochen nach 42s - 0 von 2 Pfad(en) gemessen",
        )
        body = _get(client, auth_headers, seeded_job).json()
        assert_monitor_contract(body)
        assert body["severity"] == 1
        assert body["state"] == "cancelled"
        assert body["last_run"]["status"] == "cancelled"
        assert "Abgebrochen" in body["message"]
        # Die Messwerte des letzten erfolgreichen Laufs bleiben erhalten
        assert body["last_success"]["at"] is not None
        assert body["last_success"]["total_bytes"] == 1073741824 + 500000000

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
# Regressionen aus dem Code-Review
# ----------------------------------------------------------------------

class TestReviewRegressions:
    def test_config_warnings_with_null_values_do_not_break_the_report(
        self, client, auth_headers, monkeypatch
    ):
        """
        Konfigurationswarnungen tragen optionale Felder, die None sein können
        (z.B. kept_created_at ohne created_at in der config.yaml). Mit einem
        strikten Dict[str, str] hätte Pydantic den Bericht genau dann
        abgebrochen, wenn es etwas zu melden gibt.
        """
        monkeypatch.setattr(
            "app.services.health.collect_config_warnings",
            lambda: [
                {
                    "type": "duplicate_slug",
                    "slug": "doppelt",
                    "removed_scan": "A",
                    "removed_created_at": None,
                    "kept_scan": "B",
                    "kept_created_at": None,
                    "message": "WARNUNG: Duplikat-Slug 'doppelt' gefunden.",
                }
            ],
        )

        response = client.get("/api/monitor/server", headers=auth_headers)
        assert response.status_code == 200, "kein 500, wenn Warnungen anliegen"
        body = response.json()
        assert body["state"] == "config_warnings"
        assert body["severity"] == 1
        assert body["warnings"][0]["kept_created_at"] is None

        # Auch der Instanz-Bericht darf daran nicht scheitern
        assert client.get("/api/monitor", headers=auth_headers).status_code == 200

    def test_newly_added_path_is_not_reported_as_failure(
        self, client, auth_headers, seeded_job
    ):
        """
        Wird ein Pfad NACH dem letzten Lauf konfiguriert, darf er nicht
        rückwirkend als fehlgeschlagen gelten - sonst stünde der Job bis zum
        nächsten Lauf auf 'partial', obwohl nichts schiefgegangen ist.
        """
        vorher = _get(client, auth_headers, seeded_job).json()
        assert vorher["state"] == "ok"
        assert vorher["last_run"]["folders_total"] == 2

        # Dritten Pfad ergänzen - der letzte Lauf kannte nur zwei
        client.put(
            f"/api/scan-jobs/{seeded_job['slug']}",
            headers=auth_headers,
            json={
                "name": seeded_job["name"],
                "nas_connection_id": seeded_job["nas_connection_id"],
                "paths": ["/design", "/photo", "/neu"],
                "interval": seeded_job["interval"],
                "enabled": True,
            },
        )

        nachher = _get(client, auth_headers, seeded_job).json()
        assert nachher["state"] == "ok", "der neue Pfad ist kein Fehler"
        assert nachher["severity"] == 0
        assert nachher["last_run"]["folders_failed"] == 0
        assert nachher["last_run"]["folders_ok"] == 2

    def test_real_failure_still_counts_after_a_restart(
        self, client, auth_headers, seeded_job
    ):
        """
        Gegenprobe: bei unveränderter Konfiguration muss ein fehlender Ordner
        weiterhin als Fehler zählen - in die Datenbank kommen nur erfolgreiche
        Ordner, ohne diesen Abgleich wären Fehler nach einem Neustart unsichtbar.
        """
        _add_result(seeded_job, folders=[("/design", 100, True)])

        body = _get(client, auth_headers, seeded_job).json()
        assert body["last_run"]["folders_ok"] == 1
        assert body["last_run"]["folders_failed"] == 1, (
            "der nicht gemeldete Ordner bleibt ein Fehler"
        )
        assert body["state"] == "partial"

    def test_deprecation_link_survives_unicode_job_names(self, client, auth_headers):
        """
        Der Status-Endpunkt akzeptiert auch Job-NAMEN, und Namen erlauben
        beliebiges Unicode. HTTP-Header sind Latin-1 - ein Emoji im Namen hätte
        den Endpunkt sonst mit 500 beendet.
        """
        name = "Fotos 📸 Archiv"
        job = _create_job(client, auth_headers, name, ["/fotos"])
        _add_result(job)

        response = client.get(f"/api/scans/{name}/status", headers=auth_headers)
        assert response.status_code == 200
        link = response.headers["Link"]
        assert link.isascii(), f"Header muss ASCII sein, war: {link!r}"
        assert "%F0%9F%93%B8" in link, "das Emoji muss percent-kodiert sein"
        assert 'rel="successor-version"' in link

    def test_deprecation_link_encodes_spaces_and_slashes(
        self, client, auth_headers
    ):
        """Leerzeichen und reservierte Zeichen dürfen das Link-Ziel nicht zerlegen"""
        name = "Sicherung / Woche"
        job = _create_job(client, auth_headers, name, ["/s"])
        _add_result(job)

        response = client.get(f"/api/scans/{job['slug']}/status", headers=auth_headers)
        assert response.status_code == 200
        assert " " not in response.headers["Link"].split(">")[0]


# ----------------------------------------------------------------------
# Fortschrittsberechnung (geteilt zwischen /progress und den Berichten)
# ----------------------------------------------------------------------

class TestProgressPercent:
    """
    Die Rechnung lag vorher inline in der /progress-Route und war ungetestet.
    Sie ist jetzt geteilt, also lohnt sie eigene Prüfungen mit Handrechnung.
    """

    def _completed(self, folders):
        """folders: Liste (name, size, dirs, files)"""
        return ScanResult(
            scan_slug="s",
            scan_name="S",
            timestamp=datetime.now(timezone.utc),
            status="completed",
            results=[
                ScanResultItem(
                    folder_name=name,
                    success=True,
                    num_dir=dirs,
                    num_file=files,
                    total_size=TotalSize(bytes=size, formatted=1.0, unit="B"),
                )
                for name, size, dirs, files in folders
            ],
        )

    def test_half_way_through_a_single_path(self):
        from app.services.monitoring import compute_progress_percent

        historical = self._completed([("/a", 1000, 10, 100)])
        progress = {
            "path_status": {
                "/a": {"total_size": 500, "num_dir": 5, "num_file": 50, "finished": False}
            }
        }
        # Alle drei Metriken bei 50 % -> 50*0.7 + 50*0.2 + 50*0.1 = 50.0
        assert compute_progress_percent(progress, historical) == pytest.approx(50.0)

    def test_weighting_follows_historical_size(self):
        """Ein fertiger großer Ordner zählt mehr als ein offener kleiner"""
        from app.services.monitoring import compute_progress_percent

        historical = self._completed([("/big", 900, 9, 90), ("/small", 100, 1, 10)])
        progress = {
            "path_status": {
                "/big": {"total_size": 900, "num_dir": 9, "num_file": 90, "finished": True},
                "/small": {"total_size": 0, "num_dir": 0, "num_file": 0, "finished": False},
            }
        }
        # Gewichte 900 und 100 -> (100 % * 900 + 0 % * 100) / 1000 = 90 %
        assert compute_progress_percent(progress, historical) == pytest.approx(90.0)

    def test_without_historical_run_no_estimate(self):
        from app.services.monitoring import compute_progress_percent

        assert compute_progress_percent({"path_status": {}}, None) is None
        empty = ScanResult(
            scan_slug="s",
            scan_name="S",
            timestamp=datetime.now(timezone.utc),
            status="completed",
            results=[],
        )
        assert compute_progress_percent({"path_status": {}}, empty) is None

    def test_paths_are_matched_regardless_of_slashes(self):
        from app.services.monitoring import compute_progress_percent

        historical = self._completed([("/a/", 1000, 10, 100)])
        progress = {
            "path_status": {
                "a": {"total_size": 1000, "num_dir": 10, "num_file": 100, "finished": True}
            }
        }
        assert compute_progress_percent(progress, historical) == pytest.approx(100.0)

    def test_empty_folder_counts_only_when_finished(self):
        """Größe 0 ist ein gültiger Messwert - das finished-Flag entscheidet"""
        from app.services.monitoring import compute_progress_percent

        historical = self._completed([("/leer", 0, 0, 0)])
        offen = {"path_status": {"/leer": {"total_size": 0, "finished": False}}}
        fertig = {"path_status": {"/leer": {"total_size": 0, "finished": True}}}
        assert compute_progress_percent(offen, historical) == pytest.approx(0.0)
        assert compute_progress_percent(fertig, historical) == pytest.approx(100.0)

    def test_no_path_status_means_no_progress_yet(self):
        """
        Solange kein Pfad Werte gemeldet hat, ist der Fortschritt 0 - auch wenn
        der Snapshot aggregierte Summen trägt. Die gewichtete Rechnung pro Pfad
        hat Vorrang; der Summen-Fallback greift erst, wenn KEIN historischer
        Pfad Gewicht hat. Verhalten unverändert gegenüber der früheren
        Inline-Rechnung in der /progress-Route.
        """
        from app.services.monitoring import compute_progress_percent

        historical = self._completed([("/a", 1000, 10, 100)])
        progress = {"path_status": {}, "total_size": 400, "num_dir": 4, "num_file": 40}
        assert compute_progress_percent(progress, historical) == pytest.approx(0.0)

    def test_unmatched_paths_are_treated_as_not_started(self):
        """Ein umbenannter Pfad findet keinen historischen Partner -> 0 %"""
        from app.services.monitoring import compute_progress_percent

        historical = self._completed([("/alt", 1000, 10, 100)])
        progress = {
            "path_status": {
                "/neu": {"total_size": 1000, "num_dir": 10, "num_file": 100,
                         "finished": True}
            }
        }
        assert compute_progress_percent(progress, historical) == pytest.approx(0.0)

    def test_progress_endpoint_still_reports_percent(
        self, client, auth_headers, seeded_job
    ):
        """Der Endpunkt liefert nach der Extraktion unverändert progress_percent"""
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        scanner_service._set_path_status(
            seeded_job["slug"],
            "/design",
            {"num_dir": 5, "num_file": 50, "total_size": 536870912, "waited": 4,
             "finished": False},
        )
        try:
            response = client.get(
                f"/api/scans/{seeded_job['slug']}/progress", headers=auth_headers
            )
            assert response.status_code == 200
            body = response.json()
        finally:
            _reset_scanner_state()

        assert set(body.keys()) == {"scan_slug", "scan_name", "status", "progress"}
        assert body["status"] == "running"
        assert "progress_percent" in body["progress"]
        assert body["progress"]["progress_percent"] is not None
        assert 0 <= body["progress"]["progress_percent"] <= 100

    def test_progress_endpoint_404_without_running_scan(
        self, client, auth_headers, seeded_job
    ):
        response = client.get(
            f"/api/scans/{seeded_job['slug']}/progress", headers=auth_headers
        )
        assert response.status_code == 404


# ----------------------------------------------------------------------
# Abbruch eines laufenden Scans
# ----------------------------------------------------------------------

class TestCancelScan:
    def test_cancel_marks_running_scan(self, client, auth_headers, seeded_job):
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        try:
            response = client.post(
                f"/api/scans/{seeded_job['slug']}/cancel", headers=auth_headers
            )
            assert response.status_code == 200
            body = response.json()
            assert body["cancelling"] is True
            assert body["scan_slug"] == seeded_job["slug"]
            assert scanner_service.is_cancel_requested(seeded_job["slug"]) is True

            # Der Monitoring-Bericht macht den angeforderten Abbruch sichtbar
            report = _get(client, auth_headers, seeded_job).json()
            assert report["run"]["cancel_requested"] is True
        finally:
            _reset_scanner_state()

    def test_cancel_without_running_scan_is_not_an_error(
        self, client, auth_headers, seeded_job
    ):
        """Ein doppelter Klick soll keine Fehlermeldung produzieren"""
        response = client.post(
            f"/api/scans/{seeded_job['slug']}/cancel", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["cancelling"] is False

    def test_cancel_unknown_slug_is_404(self, client, auth_headers):
        response = client.post(
            "/api/scans/gibtsnicht/cancel", headers=auth_headers
        )
        assert response.status_code == 404

    def test_cancel_needs_login_token(self, client, api_token_headers, seeded_job):
        """Read-only API-Tokens dürfen nur GET - kein Abbrechen"""
        response = client.post(
            f"/api/scans/{seeded_job['slug']}/cancel", headers=api_token_headers
        )
        assert response.status_code == 403

    def test_cancel_requires_authentication(self, client, seeded_job):
        assert client.post(f"/api/scans/{seeded_job['slug']}/cancel").status_code == 401

    def test_cancel_flag_does_not_leak_into_next_run(
        self, client, auth_headers, seeded_job
    ):
        """Ein alter Abbruchwunsch darf den nächsten Lauf nicht sofort beenden"""
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        client.post(f"/api/scans/{seeded_job['slug']}/cancel", headers=auth_headers)
        assert scanner_service.is_cancel_requested(seeded_job["slug"]) is True

        scanner_service._finish_scan(seeded_job["slug"])
        assert scanner_service.is_cancel_requested(seeded_job["slug"]) is False

        _reset_scanner_state()
        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        try:
            assert scanner_service.is_cancel_requested(seeded_job["slug"]) is False
        finally:
            _reset_scanner_state()

    def test_cancel_during_grace_period_does_nothing(
        self, client, auth_headers, seeded_job
    ):
        """
        Nach dem Ende gilt ein Scan 5 s lang noch als "laufend" (fürs Frontend).
        Ein Abbruch in diesem Fenster würde nur den nächsten Lauf belasten.
        """
        from app.services.scanner import scanner_service

        assert scanner_service._try_start_scan(seeded_job["slug"]) is True
        scanner_service._finish_scan(seeded_job["slug"])
        try:
            assert scanner_service.is_scan_running(seeded_job["slug"]) is True
            response = client.post(
                f"/api/scans/{seeded_job['slug']}/cancel", headers=auth_headers
            )
            assert response.json()["cancelling"] is False
            assert scanner_service.is_cancel_requested(seeded_job["slug"]) is False
        finally:
            _reset_scanner_state()


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
