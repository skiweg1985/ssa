"""Persistenz-Layer für Scan-Jobs und NAS-Verbindungen (SQLite).

Die Datenbank (gleiche Datei wie die Scan-Historie) ist die einzige Quelle
der Wahrheit für Jobs und NAS-Verbindungen. NAS-Passwörter werden per Fernet
verschlüsselt gespeichert (siehe app/services/security.py).

Bestehende config.yaml-Scans werden beim ersten Start einmalig importiert
(Marker in app_meta), danach wird die YAML für Jobs nicht mehr gelesen.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.config import NASConfigYAML, ScanTaskConfigYAML
from app.services.security import decrypt_secret, encrypt_secret
from app.utils.slug import generate_slug

logger = logging.getLogger(__name__)

IMPORT_MARKER_KEY = "config_yaml_imported"

# Aktueller Stand des Schemas (PRAGMA user_version). Bei jeder neuen
# Migrationsstufe hochzählen und in _migrate() einen Block ergänzen.
SCHEMA_VERSION = 1


class JobsStoreError(Exception):
    """Basisklasse für Fehler des Jobs-Stores"""


class ConnectionInUseError(JobsStoreError):
    """NAS-Verbindung wird noch von Scan-Jobs referenziert"""

    def __init__(self, job_names: List[str]):
        self.job_names = job_names
        super().__init__(
            "Verbindung wird noch verwendet von: " + ", ".join(job_names)
        )


class NotFoundError(JobsStoreError):
    """Datensatz nicht gefunden"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_or_none(value: Optional[List[str]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(list(value))


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    """
    Spaltenwert einer Row, mit Default für (noch) nicht vorhandene Spalten.

    sqlite3.Row kennt kein .get(); der Zugriff auf eine unbekannte Spalte wirft
    IndexError. Das trifft Test-Fixtures, die Rows ohne die migrierten Spalten
    bauen.
    """
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


# Voreinstellungen für den SNMP-Zugang (siehe Synology DiskStation MIB Guide)
DEFAULT_SNMP_VERSION = "2c"
DEFAULT_SNMP_PORT = 161


def _encrypt_snmp_secrets(secrets: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Verschlüsselt die SNMP-Zugangsdaten als JSON.

    Ein einzelnes verschlüsseltes Feld statt einer Spalte je Credential:
    v2c braucht nur eine Community, v3 dagegen Benutzer plus Auth- und
    Priv-Schlüssel - und spätere Felder kommen so ohne Migration aus.
    """
    if not secrets:
        return None
    return encrypt_secret(json.dumps(secrets, separators=(",", ":")))


def _list_or_none(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


class JobsStore:
    """SQLite-Store für NAS-Verbindungen und Scan-Jobs"""

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """Context Manager für Datenbankverbindungen (Muster wie ScanStorage)"""
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10.0,
            check_same_thread=False,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_database(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nas_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    host TEXT NOT NULL,
                    port INTEGER,
                    use_https INTEGER NOT NULL DEFAULT 1,
                    verify_ssl INTEGER NOT NULL DEFAULT 1,
                    username TEXT NOT NULL,
                    password_encrypted TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scan_jobs (
                    slug TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    nas_connection_id INTEGER NOT NULL REFERENCES nas_connections(id),
                    shares TEXT,
                    folders TEXT,
                    paths TEXT,
                    interval TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                );
                """
            )
            self._migrate(conn)
            conn.commit()

    # ------------------------------------------------------------------
    # Schema-Migrationen
    # ------------------------------------------------------------------

    @staticmethod
    def _add_missing_columns(
        conn: sqlite3.Connection, table: str, columns: Dict[str, str]
    ) -> None:
        """
        Fügt fehlende Spalten per ALTER TABLE hinzu.

        Idempotent über PRAGMA table_info, damit ein erneuter Lauf auf einer
        bereits migrierten (oder von Hand angepassten) Datenbank nicht bricht.
        """
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                logger.info(f"Schema-Migration: {table}.{column} ergänzt")

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """
        Bringt eine bestehende Datenbank auf SCHEMA_VERSION.

        Das CREATE-Script oben bildet bewusst nur das Ur-Schema ab; alles
        Spätere kommt ausschließlich aus diesen Stufen. So gibt es für jede
        Erweiterung genau eine Wahrheit - egal ob die Datenbank neu angelegt
        oder aus einer älteren Version übernommen wurde.
        """
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version >= SCHEMA_VERSION:
            return

        if version < 1:
            # SNMP-Zugang je NAS-Verbindung (Systemmetriken via SNMP).
            # Die Zugangsdaten liegen als verschlüsseltes JSON in einer
            # einzigen Spalte - so brauchen spätere Felder keine Migration.
            self._add_missing_columns(
                conn,
                "nas_connections",
                {
                    "snmp_enabled": "INTEGER NOT NULL DEFAULT 0",
                    "snmp_version": "TEXT",
                    "snmp_port": "INTEGER",
                    "snmp_secrets_encrypted": "TEXT",
                },
            )

        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ------------------------------------------------------------------
    # app_meta
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # NAS-Verbindungen
    # ------------------------------------------------------------------

    def _connection_row_to_dict(
        self, row: sqlite3.Row, job_count: int = 0
    ) -> Dict[str, Any]:
        """
        Öffentliche Sicht einer Verbindung.

        Enthält bewusst weder password_encrypted noch snmp_secrets_encrypted -
        diese Dicts gehen unverändert an die API-Antworten.
        """
        return {
            "id": row["id"],
            "name": row["name"],
            "host": row["host"],
            "port": row["port"],
            "use_https": bool(row["use_https"]),
            "verify_ssl": bool(row["verify_ssl"]),
            "username": row["username"],
            "snmp_enabled": bool(_row_value(row, "snmp_enabled", 0)),
            "snmp_version": _row_value(row, "snmp_version", DEFAULT_SNMP_VERSION),
            "snmp_port": _row_value(row, "snmp_port", DEFAULT_SNMP_PORT),
            "job_count": job_count,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_connections(self) -> List[Dict[str, Any]]:
        """Alle NAS-Verbindungen (ohne Passwörter), inkl. Anzahl referenzierender Jobs"""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT c.*, COUNT(j.slug) AS job_count
                FROM nas_connections c
                LEFT JOIN scan_jobs j ON j.nas_connection_id = c.id
                GROUP BY c.id
                ORDER BY c.name COLLATE NOCASE
                """
            ).fetchall()
            return [
                self._connection_row_to_dict(row, row["job_count"]) for row in rows
            ]

    def get_connection_row(self, connection_id: int) -> Optional[Dict[str, Any]]:
        """Rohdaten einer Verbindung inkl. verschlüsseltem Passwort (nur intern nutzen!)"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM nas_connections WHERE id = ?", (connection_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_connection(self, connection_id: int) -> Optional[Dict[str, Any]]:
        """Öffentliche Sicht einer Verbindung (ohne Passwort)"""
        row = self.get_connection_row(connection_id)
        if row is None:
            return None
        return self._connection_row_to_dict(row, self.job_count(connection_id))

    def get_connection_by_identifier(
        self, identifier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Verbindung per numerischer ID ODER Name (analog zu get_job).

        Namen sind UNIQUE und überleben ein Neuanlegen der Verbindung nicht -
        Monitoring-URLs bleiben damit stabiler als mit reinen IDs.
        """
        if identifier.isdigit():
            connection = self.get_connection(int(identifier))
            if connection is not None:
                return connection
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM nas_connections WHERE name = ?", (identifier,)
            ).fetchone()
        if row is None:
            return None
        return self._connection_row_to_dict(row, self.job_count(row["id"]))

    def get_connection_password(self, connection_id: int) -> str:
        """Entschlüsseltes Passwort einer Verbindung (nur Backend-intern)"""
        row = self.get_connection_row(connection_id)
        if row is None:
            raise NotFoundError(f"NAS-Verbindung {connection_id} nicht gefunden")
        return decrypt_secret(row["password_encrypted"])

    def get_snmp_config(self, connection_id: int) -> Optional[Dict[str, Any]]:
        """
        Entschlüsselter SNMP-Zugang einer Verbindung (nur Backend-intern).

        Returns:
            Dict mit host, port, version und den Zugangsdaten, oder None wenn
            SNMP für diese Verbindung nicht aktiviert ist.

        Raises:
            NotFoundError: Verbindung existiert nicht
            SecretDecryptionError: gespeicherte Zugangsdaten nicht lesbar
        """
        row = self.get_connection_row(connection_id)
        if row is None:
            raise NotFoundError(f"NAS-Verbindung {connection_id} nicht gefunden")
        if not _row_value(row, "snmp_enabled", 0):
            return None

        secrets_raw = _row_value(row, "snmp_secrets_encrypted")
        try:
            secrets = json.loads(decrypt_secret(secrets_raw)) if secrets_raw else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"SNMP-Zugangsdaten der Verbindung {connection_id} sind unlesbar"
            )
            secrets = {}

        return {
            "host": row["host"],
            "port": int(_row_value(row, "snmp_port", DEFAULT_SNMP_PORT)),
            "version": str(_row_value(row, "snmp_version", DEFAULT_SNMP_VERSION)),
            "secrets": secrets,
        }

    def job_count(self, connection_id: int) -> int:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM scan_jobs WHERE nas_connection_id = ?",
                (connection_id,),
            ).fetchone()
            return int(row["n"])

    def create_connection(
        self,
        name: str,
        host: str,
        username: str,
        password: str,
        port: Optional[int] = None,
        use_https: bool = True,
        verify_ssl: bool = True,
        snmp_enabled: bool = False,
        snmp_version: Optional[str] = None,
        snmp_port: Optional[int] = None,
        snmp_secrets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _now_iso()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO nas_connections
                    (name, host, port, use_https, verify_ssl, username,
                     password_encrypted, snmp_enabled, snmp_version, snmp_port,
                     snmp_secrets_encrypted, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    host,
                    port,
                    int(use_https),
                    int(verify_ssl),
                    username,
                    encrypt_secret(password),
                    int(snmp_enabled),
                    snmp_version or DEFAULT_SNMP_VERSION,
                    snmp_port or DEFAULT_SNMP_PORT,
                    _encrypt_snmp_secrets(snmp_secrets),
                    now,
                    now,
                ),
            )
            conn.commit()
            new_id = cursor.lastrowid
        connection = self.get_connection(new_id)
        assert connection is not None
        return connection

    def update_connection(
        self,
        connection_id: int,
        name: str,
        host: str,
        username: str,
        password: Optional[str] = None,
        port: Optional[int] = None,
        use_https: bool = True,
        verify_ssl: bool = True,
        snmp_enabled: bool = False,
        snmp_version: Optional[str] = None,
        snmp_port: Optional[int] = None,
        snmp_secrets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Aktualisiert eine Verbindung.

        Leeres/None-Passwort behält das gespeicherte - für die SNMP-Zugangsdaten
        gilt dasselbe, damit die Edit-Form ohne erneute Eingabe speichern kann.
        Auch beim Abschalten von SNMP bleiben sie erhalten.
        """
        existing = self.get_connection_row(connection_id)
        if existing is None:
            raise NotFoundError(f"NAS-Verbindung {connection_id} nicht gefunden")

        password_encrypted = (
            encrypt_secret(password) if password else existing["password_encrypted"]
        )
        snmp_secrets_encrypted = _encrypt_snmp_secrets(snmp_secrets) or _row_value(
            existing, "snmp_secrets_encrypted"
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE nas_connections
                SET name = ?, host = ?, port = ?, use_https = ?, verify_ssl = ?,
                    username = ?, password_encrypted = ?, snmp_enabled = ?,
                    snmp_version = ?, snmp_port = ?, snmp_secrets_encrypted = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    host,
                    port,
                    int(use_https),
                    int(verify_ssl),
                    username,
                    password_encrypted,
                    int(snmp_enabled),
                    snmp_version or DEFAULT_SNMP_VERSION,
                    snmp_port or DEFAULT_SNMP_PORT,
                    snmp_secrets_encrypted,
                    _now_iso(),
                    connection_id,
                ),
            )
            conn.commit()
        connection = self.get_connection(connection_id)
        assert connection is not None
        return connection

    def delete_connection(self, connection_id: int) -> None:
        """Löscht eine Verbindung. Wirft ConnectionInUseError bei referenzierenden Jobs."""
        if self.get_connection_row(connection_id) is None:
            raise NotFoundError(f"NAS-Verbindung {connection_id} nicht gefunden")
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM scan_jobs WHERE nas_connection_id = ? ORDER BY name",
                (connection_id,),
            ).fetchall()
            if rows:
                raise ConnectionInUseError([row["name"] for row in rows])
            conn.execute(
                "DELETE FROM nas_connections WHERE id = ?", (connection_id,)
            )
            conn.commit()

    def find_connection(
        self,
        host: str,
        username: str,
        port: Optional[int],
        use_https: bool,
    ) -> Optional[Dict[str, Any]]:
        """Sucht eine Verbindung anhand des Dedupe-Schlüssels (für den YAML-Import)"""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM nas_connections
                WHERE host = ? AND username = ? AND port IS ? AND use_https = ?
                """,
                (host, username, port, int(use_https)),
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Scan-Jobs
    # ------------------------------------------------------------------

    def _job_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "slug": row["slug"],
            "name": row["name"],
            "nas_connection_id": row["nas_connection_id"],
            "shares": _list_or_none(row["shares"]),
            "folders": _list_or_none(row["folders"]),
            "paths": _list_or_none(row["paths"]),
            "interval": row["interval"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM scan_jobs ORDER BY created_at"
            ).fetchall()
            return [self._job_row_to_dict(row) for row in rows]

    def get_job(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Job per Slug ODER Name (Slug hat Vorrang, wie get_scan_config bisher)"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM scan_jobs WHERE slug = ?", (identifier,)
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM scan_jobs WHERE name = ?", (identifier,)
                ).fetchone()
            return self._job_row_to_dict(row) if row else None

    def _unique_slug(self, conn: sqlite3.Connection, base_slug: str) -> str:
        slug = base_slug
        counter = 1
        while conn.execute(
            "SELECT 1 FROM scan_jobs WHERE slug = ?", (slug,)
        ).fetchone():
            counter += 1
            slug = f"{base_slug}-{counter}"
        return slug

    def create_job(
        self,
        name: str,
        nas_connection_id: int,
        interval: str,
        enabled: bool = True,
        shares: Optional[List[str]] = None,
        folders: Optional[List[str]] = None,
        paths: Optional[List[str]] = None,
        slug: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.get_connection_row(nas_connection_id) is None:
            raise NotFoundError(
                f"NAS-Verbindung {nas_connection_id} nicht gefunden"
            )
        now = _now_iso()
        with self._get_connection() as conn:
            final_slug = self._unique_slug(conn, slug or generate_slug(name))
            conn.execute(
                """
                INSERT INTO scan_jobs
                    (slug, name, nas_connection_id, shares, folders, paths,
                     interval, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    final_slug,
                    name,
                    nas_connection_id,
                    _json_or_none(shares),
                    _json_or_none(folders),
                    _json_or_none(paths),
                    interval,
                    int(enabled),
                    created_at or now,
                    now,
                ),
            )
            conn.commit()
        job = self.get_job(final_slug)
        assert job is not None
        return job

    def update_job(
        self,
        slug: str,
        name: str,
        nas_connection_id: int,
        interval: str,
        enabled: bool,
        shares: Optional[List[str]] = None,
        folders: Optional[List[str]] = None,
        paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Aktualisiert einen Job. Der Slug ist unveränderlich (Historie bleibt intakt)."""
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT slug FROM scan_jobs WHERE slug = ?", (slug,)
            ).fetchone()
            if existing is None:
                raise NotFoundError(f"Scan-Job '{slug}' nicht gefunden")
        if self.get_connection_row(nas_connection_id) is None:
            raise NotFoundError(
                f"NAS-Verbindung {nas_connection_id} nicht gefunden"
            )
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE scan_jobs
                SET name = ?, nas_connection_id = ?, shares = ?, folders = ?,
                    paths = ?, interval = ?, enabled = ?, updated_at = ?
                WHERE slug = ?
                """,
                (
                    name,
                    nas_connection_id,
                    _json_or_none(shares),
                    _json_or_none(folders),
                    _json_or_none(paths),
                    interval,
                    int(enabled),
                    _now_iso(),
                    slug,
                ),
            )
            conn.commit()
        job = self.get_job(slug)
        assert job is not None
        return job

    def delete_job(self, slug: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM scan_jobs WHERE slug = ?", (slug,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise NotFoundError(f"Scan-Job '{slug}' nicht gefunden")

    # ------------------------------------------------------------------
    # API-Tokens (statisch, read-only - für Monitoring-Systeme wie PRTG)
    # ------------------------------------------------------------------

    def list_api_tokens(self) -> List[Dict[str, Any]]:
        """Alle API-Tokens (nur Metadaten, nie der Token selbst)"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at, last_used_at FROM api_tokens "
                "ORDER BY created_at"
            ).fetchall()
            return [dict(row) for row in rows]

    def create_api_token(self, name: str) -> Dict[str, Any]:
        """
        Erzeugt ein neues API-Token.

        Returns:
            Dict mit Metadaten UND dem Klartext-Token ('token') -
            der Klartext ist nur in dieser Response verfügbar, gespeichert
            wird ausschließlich der SHA-256-Hash.
        """
        from app.services.security import generate_api_token, hash_api_token

        token = generate_api_token()
        now = _now_iso()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO api_tokens (name, token_hash, created_at) "
                "VALUES (?, ?, ?)",
                (name, hash_api_token(token), now),
            )
            conn.commit()
            new_id = cursor.lastrowid
        return {
            "id": new_id,
            "name": name,
            "created_at": now,
            "last_used_at": None,
            "token": token,
        }

    def delete_api_token(self, token_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM api_tokens WHERE id = ?", (token_id,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise NotFoundError(f"API-Token {token_id} nicht gefunden")

    def verify_api_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Prüft ein präsentiertes API-Token gegen die gespeicherten Hashes.
        Aktualisiert bei Erfolg last_used_at. Liefert die Token-Metadaten oder None.
        """
        import hmac as hmac_mod

        from app.services.security import hash_api_token

        presented_hash = hash_api_token(token)
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, token_hash FROM api_tokens"
            ).fetchall()
            match = None
            for row in rows:
                # Konstante Vergleichszeit pro Eintrag
                if hmac_mod.compare_digest(row["token_hash"], presented_hash):
                    match = row
            if match is None:
                return None
            conn.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                (_now_iso(), match["id"]),
            )
            conn.commit()
            return {"id": match["id"], "name": match["name"]}

    # ------------------------------------------------------------------
    # Bridge zu den bestehenden Pydantic-Modellen (Scanner/Scheduler)
    # ------------------------------------------------------------------

    def to_scan_config(self, job: Dict[str, Any]) -> ScanTaskConfigYAML:
        """
        Baut aus einem Job-Datensatz ein ScanTaskConfigYAML (inkl. entschlüsseltem
        NAS-Passwort), sodass scanner_service.run_scan und
        scheduler_service.add_scan_job unverändert weiterarbeiten.
        """
        connection = self.get_connection_row(job["nas_connection_id"])
        if connection is None:
            raise NotFoundError(
                f"NAS-Verbindung {job['nas_connection_id']} für Job "
                f"'{job['slug']}' nicht gefunden"
            )
        nas = NASConfigYAML(
            host=connection["host"],
            username=connection["username"],
            password=decrypt_secret(connection["password_encrypted"]),
            port=connection["port"],
            use_https=bool(connection["use_https"]),
            verify_ssl=bool(connection["verify_ssl"]),
        )
        created_at = None
        if job.get("created_at"):
            try:
                created_at = datetime.fromisoformat(job["created_at"])
            except ValueError:
                created_at = None
        return ScanTaskConfigYAML(
            name=job["name"],
            slug=job["slug"],
            created_at=created_at,
            nas=nas,
            shares=job.get("shares"),
            folders=job.get("folders"),
            paths=job.get("paths"),
            interval=job["interval"],
            enabled=job["enabled"],
        )

    # ------------------------------------------------------------------
    # Einmaliger Import aus config.yaml
    # ------------------------------------------------------------------

    def import_from_config_yaml(self) -> Dict[str, Any]:
        """
        Importiert Scans aus config.yaml — genau einmal (Marker in app_meta).

        NAS-Verbindungen werden nach (host, username, port, use_https)
        dedupliziert; Verbindungsname = host bzw. "host (username)" bei Kollision.
        """
        if self.get_meta(IMPORT_MARKER_KEY) is not None:
            return {"imported": False, "reason": "bereits importiert"}

        try:
            from app.config.loader import load_config

            config = load_config()
        except Exception as e:
            logger.warning(
                f"config.yaml-Import übersprungen (keine/ungültige Konfiguration): {e}"
            )
            self.set_meta(IMPORT_MARKER_KEY, _now_iso())
            return {"imported": False, "reason": str(e)}

        imported_jobs = 0
        created_connections = 0
        for scan in config.scans:
            nas = scan.nas
            connection = self.find_connection(
                nas.host, nas.username, nas.port, nas.use_https
            )
            if connection is None:
                base_name = nas.host
                name = base_name
                with self._get_connection() as conn:
                    if conn.execute(
                        "SELECT 1 FROM nas_connections WHERE name = ?", (name,)
                    ).fetchone():
                        name = f"{base_name} ({nas.username})"
                connection = self.create_connection(
                    name=name,
                    host=nas.host,
                    username=nas.username,
                    password=nas.password,
                    port=nas.port,
                    use_https=nas.use_https,
                    verify_ssl=nas.verify_ssl,
                )
                created_connections += 1

            self.create_job(
                name=scan.name,
                nas_connection_id=connection["id"],
                interval=scan.interval,
                enabled=scan.enabled,
                shares=scan.shares,
                folders=scan.folders,
                paths=scan.paths,
                slug=scan.slug,
                created_at=scan.created_at.isoformat() if scan.created_at else None,
            )
            imported_jobs += 1

        self.set_meta(IMPORT_MARKER_KEY, _now_iso())
        logger.info(
            f"config.yaml importiert: {imported_jobs} Job(s), "
            f"{created_connections} NAS-Verbindung(en)"
        )
        return {
            "imported": True,
            "jobs": imported_jobs,
            "connections": created_connections,
        }


# ----------------------------------------------------------------------
# Singleton (Muster wie storage)
# ----------------------------------------------------------------------

_jobs_store_instance: Optional[JobsStore] = None


def initialize_jobs_store(db_path: Path) -> JobsStore:
    """Initialisiert den Jobs-Store (im Lifespan, nach dem Storage)"""
    global _jobs_store_instance
    _jobs_store_instance = JobsStore(db_path)
    return _jobs_store_instance


def get_jobs_store() -> JobsStore:
    global _jobs_store_instance
    if _jobs_store_instance is None:
        # Fallback: gleiche Pfad-Logik wie der Storage-Default
        from app.services.storage import get_storage

        _jobs_store_instance = JobsStore(get_storage().db_path)
    return _jobs_store_instance


class JobsStoreWrapper:
    """Wrapper, der immer die aktuelle Instanz liefert (Muster wie StorageWrapper)"""

    def __getattr__(self, name):
        return getattr(get_jobs_store(), name)


jobs_store = JobsStoreWrapper()
