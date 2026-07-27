"""Regressionstest: folder_name muss vor und nach einem Server-Neustart identisch sein.

Hintergrund: Die DB speichert Pfade normalisiert OHNE führenden Slash,
der Scanner liefert Pfade MIT Slash. Vor dem Fix lieferte die API nach
einem Neustart (Ergebnisse aus der DB geladen) "design" statt "/design" -
Monitoring-Filter (z.B. PRTG-JSONPath auf folder_name) liefen dann ins Leere.
"""
from datetime import datetime, timezone

from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.storage import ScanStorage


def _make_result() -> ScanResult:
    return ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=datetime.now(timezone.utc),
        status="completed",
        results=[
            ScanResultItem(
                folder_name="/design",
                success=True,
                num_dir=10,
                num_file=100,
                total_size=TotalSize(bytes=123456789, formatted=117.7, unit="MB"),
                elapsed_time_ms=1500,
            ),
            ScanResultItem(
                folder_name="/photo/urlaub",
                success=True,
                num_dir=5,
                num_file=50,
                total_size=TotalSize(bytes=987654, formatted=0.9, unit="MB"),
                elapsed_time_ms=800,
            ),
        ],
    )


def test_folder_name_stable_across_restart(tmp_path):
    db_path = tmp_path / "history.db"

    # 1. Scan-Ergebnis speichern (wie nach einem Scan-Lauf)
    storage1 = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    storage1.add_result("design-scan", "Design Scan", _make_result(), "nas.local")

    # In-Memory: Pfade mit fuehrendem Slash (direkt vom Scanner)
    latest = storage1.get_latest_result("design-scan")
    assert latest is not None
    assert [i.folder_name for i in latest.results] == ["/design", "/photo/urlaub"]

    # 2. "Neustart": neue Storage-Instanz laedt aus derselben DB
    storage2 = ScanStorage(db_path=db_path, auto_cleanup_enabled=False)
    latest_after_restart = storage2.get_latest_result("design-scan")
    assert latest_after_restart is not None

    # folder_name muss IDENTISCH zur In-Memory-Darstellung sein
    assert [i.folder_name for i in latest_after_restart.results] == [
        "/design",
        "/photo/urlaub",
    ], "folder_name muss nach Neustart weiterhin mit fuehrendem Slash kommen"

    # Groessenwerte unveraendert
    assert latest_after_restart.results[0].total_size.bytes == 123456789
