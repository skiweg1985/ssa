"""Regressionstest: Reihenfolge der Scan-Ergebnisse muss nach einem Neustart stimmen.

Hintergrund: Die DB wurde mit `ORDER BY ... timestamp DESC` geladen, während
`add_result` neue Läufe hinten anhängt. `get_latest_result()` nimmt `[-1]` und
lieferte nach einem Serverstart deshalb den ÄLTESTEN statt den neuesten Lauf -
last_run, Status und die PRTG-Alters-Kanäle waren dadurch verfälscht, bis der
Job einmal neu lief.
"""
from datetime import datetime, timedelta, timezone

from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.storage import ScanStorage


def _make_result(timestamp: datetime, size_bytes: int, status: str = "completed") -> ScanResult:
    return ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=timestamp,
        status=status,
        results=[
            ScanResultItem(
                folder_name="/design",
                success=True,
                num_dir=10,
                num_file=100,
                total_size=TotalSize(bytes=size_bytes, formatted=1.0, unit="MB"),
                elapsed_time_ms=1500,
            )
        ],
    )


def _seed(db_path, count: int = 3) -> list:
    """Legt `count` Läufe mit aufsteigenden Timestamps an (ältester zuerst)"""
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    base = datetime.now(timezone.utc) - timedelta(hours=count)
    timestamps = []
    for i in range(count):
        ts = base + timedelta(hours=i)
        timestamps.append(ts)
        storage.add_result(
            "design-scan", "Design Scan", _make_result(ts, 1000 + i), "nas.local"
        )
    return timestamps


def test_latest_result_is_newest_after_restart(tmp_path):
    db_path = tmp_path / "history.db"
    timestamps = _seed(db_path)

    # "Neustart": frische Instanz laedt alles aus der DB
    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)

    latest = restarted.get_latest_result("design-scan")
    assert latest is not None
    assert latest.timestamp == timestamps[-1], (
        "get_latest_result muss nach einem Neustart den NEUESTEN Lauf liefern"
    )


def test_all_results_sorted_ascending_after_restart(tmp_path):
    db_path = tmp_path / "history.db"
    timestamps = _seed(db_path)

    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    results = restarted.get_all_results("design-scan")

    assert [r.timestamp for r in results] == timestamps, (
        "Reihenfolge muss aufsteigend sein - identisch zum Live-Zustand"
    )


def test_ordering_matches_live_state(tmp_path):
    """Die Reihenfolge vor und nach einem Neustart muss identisch sein."""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    for i in range(3):
        storage.add_result(
            "design-scan",
            "Design Scan",
            _make_result(base + timedelta(hours=i), 1000 + i),
            "nas.local",
        )

    live_order = [r.timestamp for r in storage.get_all_results("design-scan")]
    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    loaded_order = [r.timestamp for r in restarted.get_all_results("design-scan")]

    assert live_order == loaded_order


def test_truncation_keeps_newest(tmp_path):
    """Bei mehr Laeufen als max_history muessen die NEUESTEN erhalten bleiben."""
    db_path = tmp_path / "history.db"
    timestamps = _seed(db_path, count=5)

    restarted = ScanStorage(
        db_path=db_path, max_history=2, auto_cleanup_enabled=False
    )
    results = restarted.get_all_results("design-scan")

    assert len(results) == 2
    assert [r.timestamp for r in results] == timestamps[-2:], (
        "Trunkierung muss die neuesten Laeufe behalten, nicht die aeltesten"
    )


def test_latest_completed_result_is_newest(tmp_path):
    """get_latest_completed_result ueberspringt failed-Laeufe und nimmt den neuesten."""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    base = datetime.now(timezone.utc) - timedelta(hours=3)

    older_completed = base
    newer_completed = base + timedelta(hours=1)
    storage.add_result(
        "design-scan", "Design Scan", _make_result(older_completed, 1000), "nas.local"
    )
    storage.add_result(
        "design-scan", "Design Scan", _make_result(newer_completed, 2000), "nas.local"
    )

    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    completed = restarted.get_latest_completed_result("design-scan")
    assert completed is not None
    assert completed.timestamp == newer_completed
    assert completed.results[0].total_size.bytes == 2000


# ----------------------------------------------------------------------
# Regressionen aus dem Audit (SSA-PR7-001 / SSA-PR7-002)
# ----------------------------------------------------------------------

def _failed_result(timestamp: datetime, error: str = "boom") -> ScanResult:
    """Fehllauf ohne erfolgreiche Items -> wird als Status-Marker persistiert"""
    return ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=timestamp,
        status="failed",
        error=error,
        results=[],
    )


def test_completed_then_failed_survives_restart(tmp_path):
    """SSA-PR7-001: Ein erfolgreicher Lauf darf nicht den Status des
    nachfolgenden Fehllaufs erben."""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    base = datetime.now(timezone.utc) - timedelta(hours=2)

    storage.add_result(
        "design-scan", "Design Scan", _make_result(base, 1000), "nas.local"
    )
    storage.add_result(
        "design-scan", "Design Scan", _failed_result(base + timedelta(hours=1)), "nas.local"
    )
    before = [(r.status, len(r.results), r.error) for r in storage.get_all_results("design-scan")]

    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    after = [(r.status, len(r.results), r.error) for r in restarted.get_all_results("design-scan")]

    assert after == before, f"Zustand nach Neustart weicht ab: {after} != {before}"

    completed = restarted.get_latest_completed_result("design-scan")
    assert completed is not None, (
        "Messwerte des letzten erfolgreichen Laufs muessen den Neustart ueberleben"
    )
    assert completed.status == "completed"
    assert completed.error is None
    assert completed.results[0].total_size.bytes == 1000


def test_failed_then_completed_survives_restart(tmp_path):
    """SSA-PR7-001: auch die umgekehrte Reihenfolge muss stimmen"""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    base = datetime.now(timezone.utc) - timedelta(hours=2)

    storage.add_result("design-scan", "Design Scan", _failed_result(base), "nas.local")
    storage.add_result(
        "design-scan", "Design Scan", _make_result(base + timedelta(hours=1), 2000), "nas.local"
    )

    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    results = restarted.get_all_results("design-scan")
    assert [r.status for r in results] == ["failed", "completed"]
    assert results[1].error is None
    assert restarted.get_latest_completed_result("design-scan").results[0].total_size.bytes == 2000


def test_multiple_folders_with_marker_survive_restart(tmp_path):
    """SSA-PR7-001: mehrere Ordnerzeilen plus nachfolgender Marker"""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    base = datetime.now(timezone.utc) - timedelta(hours=2)

    multi = ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=base,
        status="completed",
        results=[
            ScanResultItem(
                folder_name=name,
                success=True,
                num_dir=1,
                num_file=1,
                total_size=TotalSize(bytes=size, formatted=1.0, unit="MB"),
                elapsed_time_ms=10,
            )
            for name, size in (("/a", 100), ("/b", 200), ("/c", 300))
        ],
    )
    storage.add_result("design-scan", "Design Scan", multi, "nas.local")
    storage.add_result(
        "design-scan", "Design Scan", _failed_result(base + timedelta(hours=1)), "nas.local"
    )

    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    completed = restarted.get_latest_completed_result("design-scan")
    assert completed is not None
    assert completed.status == "completed"
    assert len(completed.results) == 3
    assert sum(i.total_size.bytes for i in completed.results) == 600


def test_two_slugs_with_mixed_status(tmp_path):
    """SSA-PR7-001: Status darf nicht ueber Slug-Grenzen hinweg auslaufen"""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    now = datetime.now(timezone.utc)

    storage.add_result("design-scan", "Design Scan", _make_result(now, 1000), "nas.local")
    other_failed = ScanResult(
        scan_slug="other-scan",
        scan_name="Other Scan",
        timestamp=now,
        status="failed",
        error="kaputt",
        results=[],
    )
    storage.add_result("other-scan", "Other Scan", other_failed, "nas.local")

    restarted = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    design = restarted.get_latest_result("design-scan")
    assert design.status == "completed"
    assert design.error is None
    assert restarted.get_latest_result("other-scan").status == "failed"


def test_zero_byte_scan_counts_as_completed(tmp_path):
    """SSA-PR7-002: ein leerer, aber erfolgreich gescannter Ordner ist gueltig"""
    db_path = tmp_path / "history.db"
    storage = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)

    empty = ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=datetime.now(timezone.utc),
        status="completed",
        results=[
            ScanResultItem(
                folder_name="/leer",
                success=True,
                num_dir=0,
                num_file=0,
                total_size=TotalSize(bytes=0, formatted=0.0, unit="B"),
                elapsed_time_ms=5,
            )
        ],
    )
    storage.add_result("design-scan", "Design Scan", empty, "nas.local")

    completed = storage.get_latest_completed_result("design-scan")
    assert completed is not None, "0 Byte ist ein gueltiger Messwert, kein Fehlen von Daten"
    assert completed.results[0].total_size.bytes == 0
