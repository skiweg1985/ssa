"""API-Routes für NAS-Verbindungen: CRUD, Verbindungstest, Verzeichnis-Browsing"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.admin import (
    BrowseEntry,
    BrowseRequest,
    BrowseResponse,
    NASConnectionCreate,
    NASConnectionPublic,
    NASConnectionUpdate,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.services.jobs_store import (
    ConnectionInUseError,
    NotFoundError,
    jobs_store,
)
from app.services.nas_session import (
    LOGIN_TIMEOUT,
    NASConnectionNotFound,
    NASCredentialsError,
    NASLoginFailed,
    NASSessionError,
    NASUnreachable,
    evict_session,
    get_session,
    make_api as _make_api,
)
from app.services.security import SecretDecryptionError

logger = logging.getLogger(__name__)

router = APIRouter()

BROWSE_TIMEOUT = 20  # Sekunden


async def _get_session(connection_id: int):
    """
    Eingeloggte SynologyAPI-Instanz, Session-Fehler auf HTTP-Status abgebildet.

    Die Session-Logik liegt in app/services/nas_session.py, weil sie mit den
    Metrik-Endpoints geteilt wird; nur die HTTP-Abbildung gehört hierher.
    """
    try:
        return await get_session(connection_id)
    except NASConnectionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NASCredentialsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (NASLoginFailed, NASUnreachable, NASSessionError) as e:
        status = 504 if "Zeitüberschreitung" in str(e) else 502
        raise HTTPException(status_code=status, detail=str(e))


# ----------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------

@router.get("", response_model=list[NASConnectionPublic])
async def list_connections():
    """Alle NAS-Verbindungen (ohne Passwörter)"""
    return jobs_store.list_connections()


@router.post("", response_model=NASConnectionPublic, status_code=201)
async def create_connection(request: NASConnectionCreate):
    """Neue NAS-Verbindung anlegen (Passwort wird verschlüsselt gespeichert)"""
    try:
        return jobs_store.create_connection(
            name=request.name,
            host=request.host,
            username=request.username,
            password=request.password,
            port=request.port,
            use_https=request.use_https,
            verify_ssl=request.verify_ssl,
            snmp_enabled=request.snmp.enabled if request.snmp else False,
            snmp_version=request.snmp.version if request.snmp else None,
            snmp_port=request.snmp.port if request.snmp else None,
            snmp_secrets=request.snmp.to_secrets() if request.snmp else None,
        )
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"Eine Verbindung mit dem Namen '{request.name}' existiert bereits",
            )
        raise


@router.put("/{connection_id}", response_model=NASConnectionPublic)
async def update_connection(connection_id: int, request: NASConnectionUpdate):
    """Verbindung aktualisieren. Leeres Passwort behält das gespeicherte."""
    # Fehlender snmp-Block heißt "unverändert", nicht "abschalten" - sonst
    # würde ein Client, der das Feld nicht kennt, SNMP stillschweigend deaktivieren.
    if request.snmp is not None:
        snmp_enabled = request.snmp.enabled
        snmp_version = request.snmp.version
        snmp_port = request.snmp.port
        snmp_secrets = request.snmp.to_secrets()
    else:
        existing = jobs_store.get_connection(connection_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"NAS-Verbindung {connection_id} nicht gefunden",
            )
        snmp_enabled = existing["snmp_enabled"]
        snmp_version = existing["snmp_version"]
        snmp_port = existing["snmp_port"]
        snmp_secrets = None  # None = gespeicherte Zugangsdaten behalten

    try:
        result = jobs_store.update_connection(
            connection_id,
            name=request.name,
            host=request.host,
            username=request.username,
            password=request.password or None,
            port=request.port,
            use_https=request.use_https,
            verify_ssl=request.verify_ssl,
            snmp_enabled=snmp_enabled,
            snmp_version=snmp_version,
            snmp_port=snmp_port,
            snmp_secrets=snmp_secrets,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"Eine Verbindung mit dem Namen '{request.name}' existiert bereits",
            )
        raise
    evict_session(connection_id)
    return result


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(connection_id: int):
    """Verbindung löschen (409, wenn noch Jobs sie verwenden)"""
    try:
        jobs_store.delete_connection(connection_id)
    except ConnectionInUseError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    evict_session(connection_id)


# ----------------------------------------------------------------------
# Verbindungstest
# ----------------------------------------------------------------------

@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest):
    """
    Testet eine NAS-Verbindung.

    - Nur id: gespeicherte Zugangsdaten verwenden
    - Inline-Felder: diese verwenden; leeres Passwort + id => gespeichertes Passwort
    """
    host = request.host
    username = request.username
    password = request.password
    port = request.port
    use_https = request.use_https
    verify_ssl = request.verify_ssl

    if request.id is not None:
        row = jobs_store.get_connection_row(request.id)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"NAS-Verbindung {request.id} nicht gefunden",
            )
        if host is None:
            # Nur id angegeben: alles aus der gespeicherten Verbindung
            host = row["host"]
            username = row["username"]
            port = row["port"]
            use_https = bool(row["use_https"])
            verify_ssl = bool(row["verify_ssl"])
        if not password:
            try:
                password = jobs_store.get_connection_password(request.id)
            except SecretDecryptionError as e:
                return TestConnectionResponse(success=False, message=str(e))

    if not host or not username or not password:
        raise HTTPException(
            status_code=422,
            detail="Host, Benutzername und Passwort (oder id) sind erforderlich",
        )

    api = _make_api(host, port, use_https, verify_ssl)
    try:
        success = await asyncio.wait_for(
            asyncio.to_thread(api.login, username, password),
            timeout=LOGIN_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return TestConnectionResponse(
            success=False,
            message="Zeitüberschreitung - NAS nicht erreichbar",
        )
    except Exception as e:
        return TestConnectionResponse(
            success=False, message=f"Verbindung fehlgeschlagen: {e}"
        )

    if not success:
        return TestConnectionResponse(
            success=False,
            message="Anmeldung fehlgeschlagen - bitte Zugangsdaten prüfen",
        )
    try:
        await asyncio.to_thread(api.logout)
    except Exception:
        pass
    return TestConnectionResponse(success=True, message="Verbindung erfolgreich")


# ----------------------------------------------------------------------
# Browse
# ----------------------------------------------------------------------

def _browse_sync(api, path: Optional[str]):
    """Synchroner Browse-Aufruf (läuft im Thread)"""
    if not path:
        shares = api.list_shared_folders(show_message=False)
        if shares is None:
            return None
        return [
            {"name": s.get("name", ""), "path": s.get("path") or f"/{s.get('name', '')}"}
            for s in shares
        ]
    files = api.list_directory(path)
    if files is None:
        return None
    return [
        {
            "name": f.get("name", ""),
            "path": f.get("path") or f"{path.rstrip('/')}/{f.get('name', '')}",
        }
        for f in files
        if f.get("isdir")
    ]


@router.post("/{connection_id}/browse", response_model=BrowseResponse)
async def browse(connection_id: int, request: BrowseRequest):
    """
    Verzeichnisse auf dem NAS auflisten.

    Ohne path: Liste der Shares. Mit path: Unterverzeichnisse des Pfads.
    """
    api = await _get_session(connection_id)
    try:
        entries = await asyncio.wait_for(
            asyncio.to_thread(_browse_sync, api, request.path),
            timeout=BROWSE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Zeitüberschreitung beim Auflisten der Verzeichnisse",
        )
    except Exception as e:
        evict_session(connection_id)
        raise HTTPException(
            status_code=502, detail=f"Fehler beim Auflisten: {e}"
        )

    if entries is None:
        # Möglicherweise abgelaufene Session: einmal frisch einloggen und erneut versuchen
        evict_session(connection_id)
        api = await _get_session(connection_id)
        try:
            entries = await asyncio.wait_for(
                asyncio.to_thread(_browse_sync, api, request.path),
                timeout=BROWSE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Zeitüberschreitung beim Auflisten der Verzeichnisse",
            )
        except Exception as e:
            evict_session(connection_id)
            raise HTTPException(
                status_code=502, detail=f"Fehler beim Auflisten: {e}"
            )
        if entries is None:
            raise HTTPException(
                status_code=502,
                detail="Verzeichnisse konnten nicht geladen werden",
            )

    return BrowseResponse(
        path=request.path,
        entries=[BrowseEntry(**e) for e in entries],
    )
