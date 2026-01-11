"""In-Memory Storage für Scan-Ergebnisse mit SQLite-Persistierung"""
import json
import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from contextlib import contextmanager
from app.models.scan import ScanResult, ScanResultItem, TotalSize

logger = logging.getLogger(__name__)


class ScanStorage:
    """In-Memory Storage für Scan-Ergebnisse mit SQLite-Persistierung"""
    
    def __init__(
        self, 
        max_history: int = 1000, 
        storage_dir: Optional[str] = None, 
        db_path: Optional[str] = None,
        auto_cleanup_days: Optional[int] = None,
        auto_cleanup_enabled: bool = True
    ):
        """
        Initialisiert den Storage
        
        Args:
            max_history: Maximale Anzahl gespeicherter Scans pro Task (älteste werden entfernt)
            storage_dir: Verzeichnis für persistierte Daten (wird ignoriert wenn db_path gesetzt)
            db_path: Pfad zur SQLite-Datenbank. Wenn None, wird ein Standard-Pfad verwendet.
            auto_cleanup_days: Anzahl Tage, nach denen alte Einträge automatisch gelöscht werden.
                              None = deaktiviert, Standard: 90 Tage
            auto_cleanup_enabled: Ob automatische Bereinigung aktiviert ist
        """
        self._results: Dict[str, List[ScanResult]] = defaultdict(list)
        self._max_history = max_history
        self._auto_cleanup_days = auto_cleanup_days if auto_cleanup_days is not None else 90
        self._auto_cleanup_enabled = auto_cleanup_enabled
        
        # Bestimme Datenbank-Pfad
        if db_path is None:
            if storage_dir is None:
                # Standard: data/ Verzeichnis im Projekt-Root
                # Versuche Projekt-Root zu finden (3 Ebenen hoch von app/services/storage.py)
                project_root = Path(__file__).parent.parent.parent
                # Fallback: Aktuelles Arbeitsverzeichnis
                if not (project_root / "config.yaml").exists():
                    project_root = Path.cwd()
                storage_dir = project_root / "data"
            else:
                storage_dir = Path(storage_dir)
            
            storage_dir.mkdir(parents=True, exist_ok=True)
            db_path = storage_dir / "history.db"
        else:
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._db_path = db_path
        
        # Initialisiere Datenbank
        self._init_database()
        
        # Lade persistierte Daten beim Start
        self._load_from_disk()
        
        # Führe automatische Bereinigung beim Start aus
        if self._auto_cleanup_enabled:
            self.cleanup_old_results(self._auto_cleanup_days)
    
    def _normalize_folder_path(self, folder_path: str) -> str:
        """
        Normalisiert einen Ordner-Pfad für konsistente Speicherung
        
        Args:
            folder_path: Pfad (kann mit oder ohne führenden Slash sein)
        
        Returns:
            Normalisierter Pfad
        """
        # Entferne führende Slashes und normalisiere
        path = folder_path.strip().lstrip('/')
        return path
    
    def _generate_primary_key(
        self, 
        nas_host: str,
        folder_path: str, 
        timestamp: datetime
    ) -> str:
        """
        Generiert einen eindeutigen Primary Key für einen Ordner-Scan-Ergebnis
        
        Primary Key = nas_host + folder_path + timestamp
        Dies macht einen Ordner eindeutig durch seine physische Position, nicht durch Scan-Namen
        
        Args:
            nas_host: Hostname/IP des NAS
            folder_path: Normalisierter Pfad des Ordners
            timestamp: Zeitstempel des Scans
        
        Returns:
            Eindeutiger String-Key
        """
        normalized_path = self._normalize_folder_path(folder_path)
        normalized_ts = timestamp.replace(microsecond=0).isoformat()
        key_string = f"{nas_host}::{normalized_path}::{normalized_ts}"
        # Erstelle Hash für kompakten Key
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    def _init_database(self) -> None:
        """Initialisiert die SQLite-Datenbank mit Tabellen"""
        with self._get_connection() as conn:
            # Lösche alte Tabelle falls vorhanden (für Migration zu slug/uid)
            conn.execute("DROP TABLE IF EXISTS scan_results")
            
            # Haupttabelle: Jeder Ordner/Pfad wird einzeln gespeichert
            # Primary Key = nas_host + folder_path + timestamp
            conn.execute("""
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
            """)
            
            # Indizes für schnelle Abfragen
            conn.execute("""
                CREATE INDEX idx_scan_slug_timestamp 
                ON scan_results(scan_slug, timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nas_folder 
                ON scan_results(nas_host, folder_path)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_folder_path 
                ON scan_results(folder_path)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nas_host 
                ON scan_results(nas_host)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON scan_results(timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON scan_results(status)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context Manager für Datenbankverbindungen"""
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10.0,
            check_same_thread=False
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB Cache
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()
    
    def _load_from_disk(self) -> None:
        """Lädt alle persistierten Ergebnisse vom Datenträger"""
        if not self._db_path.exists():
            return
        
        try:
            with self._get_connection() as conn:
                # Lade alle Ordner-Ergebnisse gruppiert nach Scan und Timestamp
                cursor = conn.execute("""
                    SELECT 
                        scan_slug,
                        scan_name,
                        timestamp,
                        nas_host,
                        folder_path,
                        status,
                        success,
                        num_dir,
                        num_file,
                        total_size_bytes,
                        total_size_formatted,
                        total_size_unit,
                        elapsed_time_ms,
                        error,
                        scan_error
                    FROM scan_results
                    ORDER BY scan_slug, timestamp DESC, folder_path
                """)
                
                current_scan_slug = None
                current_scan_name = None
                current_timestamp = None
                results_for_scan = []
                items_for_result = []
                
                for row in cursor.fetchall():
                    (scan_slug, scan_name, timestamp_str, nas_host, folder_path, status, success,
                     num_dir, num_file, total_size_bytes, total_size_formatted,
                     total_size_unit, elapsed_time_ms, error, scan_error) = row
                    
                    timestamp = datetime.fromisoformat(timestamp_str)
                    
                    # Überspringe Marker-Einträge (werden separat als ScanResult mit Status behandelt)
                    if folder_path == "__SCAN_STATUS_MARKER__":
                        # Speichere vorherige Gruppe falls vorhanden
                        if items_for_result and current_scan_slug:
                            result = ScanResult(
                                scan_slug=current_scan_slug,
                                scan_name=current_scan_name,
                                timestamp=current_timestamp,
                                status=status,
                                error=scan_error,
                                results=items_for_result
                            )
                            results_for_scan.append(result)
                            items_for_result = []
                        
                        # Neue ScanResult-Gruppe für Marker?
                        if (current_scan_slug and current_scan_slug != scan_slug) or \
                           (current_timestamp and current_timestamp != timestamp):
                            # Neue Scan-Gruppe?
                            if current_scan_slug and current_scan_slug != scan_slug:
                                if len(results_for_scan) > self._max_history:
                                    results_for_scan = results_for_scan[:self._max_history]
                                self._results[current_scan_slug] = results_for_scan
                                results_for_scan = []
                        
                        # Erstelle ScanResult für fehlgeschlagenen Scan (ohne erfolgreiche Ergebnisse)
                        result = ScanResult(
                            scan_slug=scan_slug,
                            scan_name=scan_name,
                            timestamp=timestamp,
                            status=status,
                            error=scan_error,
                            results=[]  # Leere results für fehlgeschlagene Scans
                        )
                        results_for_scan.append(result)
                        
                        current_scan_slug = scan_slug
                        current_scan_name = scan_name
                        current_timestamp = timestamp
                        continue
                    
                    # Neue ScanResult-Gruppe?
                    if (current_scan_slug and current_scan_slug != scan_slug) or \
                       (current_timestamp and current_timestamp != timestamp):
                        if items_for_result:
                            result = ScanResult(
                                scan_slug=current_scan_slug,
                                scan_name=current_scan_name,
                                timestamp=current_timestamp,
                                status=status,
                                error=scan_error,
                                results=items_for_result
                            )
                            results_for_scan.append(result)
                            items_for_result = []
                        
                        # Neue Scan-Gruppe?
                        if current_scan_slug and current_scan_slug != scan_slug:
                            if len(results_for_scan) > self._max_history:
                                results_for_scan = results_for_scan[:self._max_history]
                            self._results[current_scan_slug] = results_for_scan
                            results_for_scan = []
                    
                    current_scan_slug = scan_slug
                    current_scan_name = scan_name
                    current_timestamp = timestamp
                    
                    # Erstelle ScanResultItem
                    total_size = None
                    if total_size_bytes is not None:
                        total_size = TotalSize(
                            bytes=total_size_bytes,
                            formatted=total_size_formatted or 0,
                            unit=total_size_unit or 'B'
                        )
                    
                    item = ScanResultItem(
                        folder_name=folder_path,
                        success=bool(success),
                        num_dir=num_dir,
                        num_file=num_file,
                        total_size=total_size,
                        elapsed_time_ms=elapsed_time_ms,
                        error=error
                    )
                    items_for_result.append(item)
                
                # Speichere letzte Gruppen
                if items_for_result and current_scan_slug:
                    result = ScanResult(
                        scan_slug=current_scan_slug,
                        scan_name=current_scan_name,
                        timestamp=current_timestamp,
                        status=status,
                        error=scan_error,
                        results=items_for_result
                    )
                    results_for_scan.append(result)
                
                if current_scan_slug:
                    if len(results_for_scan) > self._max_history:
                        results_for_scan = results_for_scan[:self._max_history]
                    self._results[current_scan_slug] = results_for_scan
                
                # Statistiken
                cursor = conn.execute("SELECT COUNT(*) FROM scan_results")
                total_count = cursor.fetchone()[0]
                if total_count > 0:
                    db_size = self._db_path.stat().st_size / (1024 * 1024)
                    print(f"Geladen: {len(self._results)} Scans, {total_count} Ordner-Einträge, {db_size:.2f} MB")
        
        except Exception as e:
            print(f"Warnung: Fehler beim Laden aus Datenbank: {e}")
    
    def _save_to_disk(self, scan_slug: str, scan_name: str, result: ScanResult, nas_host: str) -> None:
        """
        Speichert ein Scan-Ergebnis in der Datenbank
        
        Args:
            scan_slug: Slug des Scans
            scan_name: Name des Scans
            result: Scan-Ergebnis
            nas_host: Hostname/IP des NAS
        """
        try:
            with self._get_connection() as conn:
                # Speichere nur erfolgreiche Ergebnisse (um 0-Werte zu vermeiden)
                successful_items = [item for item in result.results if item.success]
                
                if successful_items:
                    # Speichere nur erfolgreiche Ordner
                    for item in successful_items:
                        normalized_path = self._normalize_folder_path(item.folder_name)
                        primary_key = self._generate_primary_key(
                            nas_host,
                            normalized_path,
                            result.timestamp
                        )
                        
                        total_size_bytes = item.total_size.bytes if item.total_size else None
                        total_size_formatted = item.total_size.formatted if item.total_size else None
                        total_size_unit = item.total_size.unit if item.total_size else None
                        
                        conn.execute("""
                            INSERT OR REPLACE INTO scan_results 
                            (id, nas_host, folder_path, scan_slug, scan_name, timestamp, status, success,
                             num_dir, num_file, total_size_bytes, total_size_formatted,
                             total_size_unit, elapsed_time_ms, error, scan_error, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            primary_key,
                            nas_host,
                            normalized_path,
                            scan_slug,
                            scan_name,
                            result.timestamp.isoformat(),
                            result.status,
                            item.success,
                            item.num_dir,
                            item.num_file,
                            total_size_bytes,
                            total_size_formatted,
                            total_size_unit,
                            item.elapsed_time_ms,
                            item.error,
                            result.error,
                            datetime.now(timezone.utc).isoformat()
                        ))
                    
                    conn.commit()
                else:
                    # Keine erfolgreichen Ergebnisse - speichere einen Marker für die Historie
                    logger.info(
                        f"Scan '{scan_slug}': Keine erfolgreichen Ergebnisse - "
                        f"speichere Status-Marker für Historie (Status: {result.status})"
                    )
                    # Verwende einen speziellen Marker-Pfad, der beim Laden gefiltert wird
                    marker_path = "__SCAN_STATUS_MARKER__"
                    primary_key = self._generate_primary_key(
                        nas_host,
                        marker_path,
                        result.timestamp
                    )
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO scan_results 
                        (id, nas_host, folder_path, scan_slug, scan_name, timestamp, status, success,
                         num_dir, num_file, total_size_bytes, total_size_formatted,
                         total_size_unit, elapsed_time_ms, error, scan_error, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        primary_key,
                        nas_host,
                        marker_path,
                        scan_slug,
                        scan_name,
                        result.timestamp.isoformat(),
                        result.status,
                        False,
                        None,
                        None,
                        None,  # Keine Größen-Daten (keine 0-Werte!)
                        None,
                        None,
                        None,
                        None,
                        result.error,
                        datetime.now(timezone.utc).isoformat()
                    ))
                    conn.commit()
                
                # Bereinige alte Einträge (behalte nur max_history pro Scan)
                conn.execute("""
                    DELETE FROM scan_results
                    WHERE scan_slug = ? 
                    AND timestamp NOT IN (
                        SELECT DISTINCT timestamp FROM scan_results
                        WHERE scan_slug = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                """, (scan_slug, scan_slug, self._max_history))
                
                conn.commit()
        
        except Exception as e:
            print(f"Warnung: Fehler beim Speichern von {scan_slug}: {e}")
    
    def add_result(self, scan_slug: str, scan_name: str, result: ScanResult, nas_host: str) -> None:
        """
        Fügt ein Scan-Ergebnis hinzu
        
        Args:
            scan_slug: Slug des Scan-Tasks
            scan_name: Name des Scan-Tasks
            result: Scan-Ergebnis
            nas_host: Hostname/IP des NAS (für Primary Key)
        """
        # Verwende slug als Key für in-memory storage
        self._results[scan_slug].append(result)
        
        if len(self._results[scan_slug]) > self._max_history:
            self._results[scan_slug] = self._results[scan_slug][-self._max_history:]
        
        self._save_to_disk(scan_slug, scan_name, result, nas_host)
    
    def update_latest_result(self, scan_slug: str, scan_name: str, result: ScanResult, nas_host: str) -> None:
        """
        Aktualisiert das neueste Ergebnis für einen Scan
        
        Args:
            scan_slug: Slug des Scan-Tasks
            scan_name: Name des Scan-Tasks
            result: Aktualisiertes Scan-Ergebnis
            nas_host: Hostname/IP des NAS (für Primary Key)
        """
        if scan_slug not in self._results or not self._results[scan_slug]:
            self.add_result(scan_slug, scan_name, result, nas_host)
        else:
            latest = self._results[scan_slug][-1]
            if latest.timestamp == result.timestamp:
                # Update des bestehenden Eintrags
                self._results[scan_slug][-1] = result
                self._save_to_disk(scan_slug, scan_name, result, nas_host)
            else:
                # Neuer Scan mit neuem Timestamp
                self.add_result(scan_slug, scan_name, result, nas_host)
    
    def get_latest_result(self, scan_slug: str) -> Optional[ScanResult]:
        """Holt das neueste Ergebnis für einen Scan (anhand slug)"""
        if scan_slug not in self._results or not self._results[scan_slug]:
            return None
        return self._results[scan_slug][-1]
    
    def get_latest_completed_result(self, scan_slug: str) -> Optional[ScanResult]:
        """
        Holt das neueste erfolgreich abgeschlossene Scan-Ergebnis (status='completed')
        
        Args:
            scan_slug: Slug des Scan-Tasks
            
        Returns:
            Das neueste erfolgreiche ScanResult oder None wenn keines vorhanden ist
        """
        if scan_slug not in self._results or not self._results[scan_slug]:
            return None
        
        # Durchsuche Ergebnisse rückwärts (neueste zuerst) nach dem ersten "completed" Status
        for result in reversed(self._results[scan_slug]):
            if result.status == "completed" and result.results:
                # Prüfe ob mindestens ein erfolgreiches Ergebnis vorhanden ist
                if any(item.success and item.total_size and item.total_size.bytes > 0 for item in result.results):
                    return result
        
        return None
    
    def get_all_results(self, scan_slug: str) -> List[ScanResult]:
        """Holt alle Ergebnisse für einen Scan (anhand slug)"""
        return self._results.get(scan_slug, [])
    
    def get_results_since(self, scan_slug: str, since: datetime) -> List[ScanResult]:
        """Holt alle Ergebnisse seit einem bestimmten Zeitpunkt"""
        all_results = self.get_all_results(scan_slug)
        return [r for r in all_results if r.timestamp >= since]
    
    def clear_results(self, scan_slug: Optional[str] = None) -> None:
        """Löscht Ergebnisse"""
        with self._get_connection() as conn:
            if scan_slug is None:
                conn.execute("DELETE FROM scan_results")
                self._results.clear()
            else:
                conn.execute("DELETE FROM scan_results WHERE scan_slug = ?", (scan_slug,))
                if scan_slug in self._results:
                    del self._results[scan_slug]
            conn.commit()
    
    def delete_folder_results(
        self,
        nas_host: Optional[str] = None,
        folder_path: Optional[str] = None,
        scan_slug: Optional[str] = None
    ) -> int:
        """
        Löscht Ergebnisse für spezifische Ordner/Pfade
        
        Args:
            nas_host: Optional: Nur für dieses NAS
            folder_path: Normalisierter Pfad des Ordners
            scan_slug: Optional: Nur für diesen Scan (anhand slug)
        
        Returns:
            Anzahl gelöschter Einträge
        """
        with self._get_connection() as conn:
            conditions = []
            params = []
            
            if nas_host:
                conditions.append("nas_host = ?")
                params.append(nas_host)
            
            if folder_path:
                normalized = self._normalize_folder_path(folder_path)
                conditions.append("folder_path = ?")
                params.append(normalized)
            
            if scan_slug:
                conditions.append("scan_slug = ?")
                params.append(scan_slug)
            
            if not conditions:
                return 0
            
            where_clause = " AND ".join(conditions)
            cursor = conn.execute(
                f"DELETE FROM scan_results WHERE {where_clause}",
                params
            )
            
            deleted = cursor.rowcount
            conn.commit()
            
            # Aktualisiere RAM-Cache
            if scan_slug and scan_slug in self._results:
                normalized = self._normalize_folder_path(folder_path) if folder_path else None
                for result in self._results[scan_slug]:
                    result.results = [
                        item for item in result.results
                        if not normalized or self._normalize_folder_path(item.folder_name) != normalized
                    ]
                # Entferne leere Ergebnisse
                self._results[scan_slug] = [
                    r for r in self._results[scan_slug] 
                    if r.results
                ]
            
            return deleted
    
    def get_all_scan_slugs(self) -> List[str]:
        """Gibt alle Scan-Slugs zurück"""
        return list(self._results.keys())
    
    def get_all_folders(
        self, 
        nas_host: Optional[str] = None,
        scan_slug: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """
        Gibt alle eindeutigen Ordner/Pfade zurück
        
        Args:
            nas_host: Optional: Nur für dieses NAS
            scan_slug: Optional: Nur für diesen Scan (anhand slug)
        
        Returns:
            Liste von Tupeln (nas_host, folder_path)
        """
        with self._get_connection() as conn:
            conditions = []
            params = []
            
            if nas_host:
                conditions.append("nas_host = ?")
                params.append(nas_host)
            
            if scan_slug:
                conditions.append("scan_slug = ?")
                params.append(scan_slug)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            cursor = conn.execute(
                f"SELECT DISTINCT nas_host, folder_path FROM scan_results WHERE {where_clause} ORDER BY nas_host, folder_path",
                params
            )
            
            return cursor.fetchall()
    
    def cleanup_old_results(
        self, 
        days: Optional[int] = None,
        nas_host: Optional[str] = None,
        folder_path: Optional[str] = None,
        scan_slug: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Löscht Ergebnisse, die älter als X Tage sind
        
        Args:
            days: Anzahl der Tage (None = verwendet auto_cleanup_days)
            nas_host: Optional: Nur für dieses NAS
            folder_path: Optional: Nur für diesen Ordner
            scan_slug: Optional: Nur für diesen Scan (anhand slug)
            dry_run: Wenn True, wird nichts gelöscht, nur Statistiken zurückgegeben
        
        Returns:
            Dictionary mit Statistiken
        """
        if days is None:
            days = self._auto_cleanup_days
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        stats = {
            'deleted_count': 0,
            'freed_space_mb': 0.0,
            'cutoff_date': cutoff.isoformat(),
            'days': days
        }
        
        with self._get_connection() as conn:
            conditions = ["timestamp < ?"]
            params = [cutoff_str]
            
            if nas_host:
                conditions.append("nas_host = ?")
                params.append(nas_host)
            
            if folder_path:
                normalized = self._normalize_folder_path(folder_path)
                conditions.append("folder_path = ?")
                params.append(normalized)
            
            if scan_slug:
                conditions.append("scan_slug = ?")
                params.append(scan_slug)
            
            where_clause = " AND ".join(conditions)
            
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM scan_results WHERE {where_clause}",
                params
            )
            
            count = cursor.fetchone()[0]
            stats['deleted_count'] = count
            
            if not dry_run and count > 0:
                estimated_size = count * 3 * 1024
                stats['freed_space_mb'] = estimated_size / (1024 * 1024)
                
                conn.execute(
                    f"DELETE FROM scan_results WHERE {where_clause}",
                    params
                )
                
                conn.commit()
                conn.execute("VACUUM")
                conn.commit()
                
                # Aktualisiere RAM-Cache
                for slug in list(self._results.keys()):
                    if scan_slug is None or slug == scan_slug:
                        self._results[slug] = [
                            r for r in self._results[slug] 
                            if r.timestamp >= cutoff
                        ]
                        if not self._results[slug]:
                            del self._results[slug]
        
        return stats
    
    def get_result_ids(
        self,
        nas_host: Optional[str] = None,
        folder_path: Optional[str] = None,
        scan_slug: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        status: Optional[str] = None
    ) -> List[Tuple[str, str, str, str]]:
        """
        Gibt IDs von Ergebnissen zurück, die bestimmten Kriterien entsprechen
        
        Returns:
            Liste von Tupeln (id, nas_host, folder_path, timestamp)
        """
        with self._get_connection() as conn:
            conditions = []
            params = []
            
            if nas_host:
                conditions.append("nas_host = ?")
                params.append(nas_host)
            
            if folder_path:
                normalized = self._normalize_folder_path(folder_path)
                conditions.append("folder_path = ?")
                params.append(normalized)
            
            if scan_slug:
                conditions.append("scan_slug = ?")
                params.append(scan_slug)
            
            if since:
                conditions.append("timestamp >= ?")
                params.append(since.isoformat())
            
            if until:
                conditions.append("timestamp <= ?")
                params.append(until.isoformat())
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            cursor = conn.execute(
                f"SELECT id, nas_host, folder_path, timestamp FROM scan_results WHERE {where_clause}",
                params
            )
            
            return cursor.fetchall()
    
    def get_storage_stats(self) -> Dict[str, any]:
        """Gibt Statistiken über den Storage zurück"""
        total_results = sum(len(results) for results in self._results.values())
        db_size = 0
        db_count = 0
        folder_count = 0
        nas_count = 0
        oldest_entry = None
        newest_entry = None
        
        if self._db_path.exists():
            try:
                db_size = self._db_path.stat().st_size
                with self._get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM scan_results")
                    db_count = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT COUNT(DISTINCT folder_path) FROM scan_results")
                    folder_count = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT COUNT(DISTINCT nas_host) FROM scan_results")
                    nas_count = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM scan_results")
                    row = cursor.fetchone()
                    if row[0]:
                        oldest_entry = row[0]
                        newest_entry = row[1]
            except Exception as e:
                print(f"Fehler beim Abrufen der Statistiken: {e}")
        
        return {
            'scan_count': len(self._results),
            'nas_count': nas_count,
            'folder_count': folder_count,
            'total_results_ram': total_results,
            'total_results_db': db_count,
            'db_size_bytes': db_size,
            'db_size_mb': db_size / (1024 * 1024),
            'max_history': self._max_history,
            'auto_cleanup_days': self._auto_cleanup_days,
            'auto_cleanup_enabled': self._auto_cleanup_enabled,
            'oldest_entry': oldest_entry,
            'newest_entry': newest_entry,
            'db_path': str(self._db_path)
        }
    
    def get_cleanup_preview(self, days: int) -> Dict[str, any]:
        """Zeigt Vorschau der Bereinigung ohne zu löschen"""
        return self.cleanup_old_results(days=days, dry_run=True)


# Globale Storage-Instanz (wird mit Defaults initialisiert, kann später mit Config überschrieben werden)
_storage_instance: Optional[ScanStorage] = None


def get_storage() -> ScanStorage:
    """Gibt die globale Storage-Instanz zurück (lazy initialization)"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = ScanStorage(max_history=1000, auto_cleanup_days=90)
    return _storage_instance


def init_storage_from_config(
    db_path: Optional[str] = None,
    storage_dir: Optional[str] = None,
    max_history: int = 1000,
    auto_cleanup_days: Optional[int] = 90
) -> ScanStorage:
    """
    Initialisiert die globale Storage-Instanz mit Konfigurationsparametern
    
    Args:
        db_path: Pfad zur SQLite-Datenbank
        storage_dir: Verzeichnis für persistierte Daten
        max_history: Maximale Anzahl gespeicherter Scans
        auto_cleanup_days: Anzahl Tage für automatische Bereinigung
    """
    global _storage_instance
    _storage_instance = ScanStorage(
        max_history=max_history,
        storage_dir=storage_dir,
        db_path=db_path,
        auto_cleanup_days=auto_cleanup_days
    )
    return _storage_instance


class StorageWrapper:
    """Wrapper-Klasse für storage, die immer die aktuelle Instanz zurückgibt"""
    def __getattr__(self, name):
        return getattr(get_storage(), name)
    
    def __call__(self, *args, **kwargs):
        return get_storage()(*args, **kwargs)


# Für Rückwärtskompatibilität: storage als Wrapper (gibt immer die aktuelle Instanz zurück)
storage = StorageWrapper()
