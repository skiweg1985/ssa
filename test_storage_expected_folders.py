"""Tests für den Sollwert `expected_folders` in der Ergebnis-Historie.

Hintergrund: In die Datenbank werden nur ERFOLGREICHE Ordner geschrieben. Ohne
die Anzahl der Ordner, die ein Lauf scannen sollte, liesse sich nach einem
Neustart nicht unterscheiden, ob ein Ordner fehlt, weil er fehlschlug, oder
weil er erst nach dem Lauf konfiguriert wurde. Der Sollwert gehört deshalb an
den Lauf - nicht an den Job, dessen Konfiguration sich ändern kann.

Geprüft werden der Roundtrip über die Datenbank und die Migration bestehender
Datenbanken, die die Spalte noch nicht haben.
"""
import sqlite3
from datetime import datetime, timezone

from app.models.scan import ScanResult, ScanResultItem, TotalSize
from app.services.storage import ScanStorage


def _result(expected_folders, folders=(("/design", True), ("/photo", True))):
    return ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=datetime.now(timezone.utc),
        status="completed",
        expected_folders=expected_folders,
        results=[
            ScanResultItem(
                folder_name=name,
                success=success,
                num_dir=10 if success else None,
                num_file=100 if success else None,
                total_size=(
                    TotalSize(bytes=1024, formatted=1.0, unit="KB") if success else None
                ),
                elapsed_time_ms=1500 if success else None,
                error=None if success else "nicht erreichbar",
            )
            for name, success in folders
        ],
    )


def test_expected_folders_survives_a_restart(tmp_path):
    """Der Sollwert muss aus der Datenbank zurückkommen"""
    db = tmp_path / "history.db"

    storage = ScanStorage(db_path=db, auto_cleanup_enabled=False)
    storage.add_result("design-scan", "Design Scan", _result(3), "nas.local")

    # Neue Instanz auf derselben Datei = Neustart
    nach_neustart = ScanStorage(db_path=db, auto_cleanup_enabled=False)
    latest = nach_neustart.get_latest_result("design-scan")

    assert latest is not None
    assert latest.expected_folders == 3, (
        "ohne diesen Wert wäre nach einem Neustart nicht erkennbar, "
        "dass ein Ordner fehlt"
    )


def test_failure_marker_run_also_keeps_the_expected_count(tmp_path):
    """Auch ein Lauf ganz ohne erfolgreiche Ordner behält den Sollwert"""
    db = tmp_path / "history.db"

    storage = ScanStorage(db_path=db, auto_cleanup_enabled=False)
    fehllauf = ScanResult(
        scan_slug="design-scan",
        scan_name="Design Scan",
        timestamp=datetime.now(timezone.utc),
        status="failed",
        error="Login fehlgeschlagen",
        expected_folders=2,
        results=[],
    )
    storage.add_result("design-scan", "Design Scan", fehllauf, "nas.local")

    nach_neustart = ScanStorage(db_path=db, auto_cleanup_enabled=False)
    latest = nach_neustart.get_latest_result("design-scan")

    assert latest is not None
    assert latest.status == "failed"
    assert latest.expected_folders == 2


def test_legacy_database_is_migrated(tmp_path):
    """
    Eine Datenbank aus einer älteren Version hat die Spalte nicht. Sie muss
    beim Öffnen ergänzt werden, ohne dass bestehende Daten verloren gehen.
    """
    db = tmp_path / "history.db"

    # Datenbank im alten Schema anlegen - ohne expected_folders
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE scan_results (
            id TEXT PRIMARY KEY,
            nas_host TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            scan_slug TEXT NOT NULL,
            scan_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            num_dir INTEGER,
            num_file INTEGER,
            total_size_bytes INTEGER,
            total_size_formatted REAL,
            total_size_unit TEXT,
            elapsed_time_ms INTEGER,
            error TEXT,
            scan_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(nas_host, folder_path, timestamp)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO scan_results
        (id, nas_host, folder_path, scan_slug, scan_name, timestamp, status,
         success, num_dir, num_file, total_size_bytes, total_size_formatted,
         total_size_unit, elapsed_time_ms, error, scan_error, created_at, updated_at)
        VALUES ('alt1', 'nas.local', 'design', 'design-scan', 'Design Scan',
                ?, 'completed', 1, 10, 100, 1024, 1.0, 'KB', 1500, NULL, NULL,
                ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # Öffnen migriert
    storage = ScanStorage(db_path=db, auto_cleanup_enabled=False)

    check = sqlite3.connect(db)
    columns = {row[1] for row in check.execute("PRAGMA table_info(scan_results)")}
    check.close()
    assert "expected_folders" in columns, "die Spalte muss ergänzt worden sein"

    # Der alte Datensatz ist weiterhin lesbar, nur ohne Sollwert
    latest = storage.get_latest_result("design-scan")
    assert latest is not None
    assert latest.expected_folders is None
    assert len(latest.results) == 1
    assert latest.results[0].folder_name == "/design"


def test_migration_is_idempotent(tmp_path):
    """Zweimaliges Öffnen darf nicht an einem doppelten ALTER TABLE scheitern"""
    db = tmp_path / "history.db"
    first = ScanStorage(db_path=db, auto_cleanup_enabled=False)
    first.add_result("design-scan", "Design Scan", _result(2), "nas.local")

    second = ScanStorage(db_path=db, auto_cleanup_enabled=False)
    assert second.get_latest_result("design-scan").expected_folders == 2
