"""Eingeloggte SynologyAPI-Sessions je NAS-Verbindung, mit Wiederverwendung.

Ausgelagert aus app/api/nas_routes.py, weil neben dem interaktiven Browsen
inzwischen auch die Metrik-Abfragen (app/services/nas_metrics.py) Sessions
brauchen. Ohne gemeinsamen Cache löst jeder Sensor-Poll einen eigenen
DSM-Login aus - bei zwei PRTG-Sensoren pro NAS im Minutentakt summiert sich
das schnell zu unnötiger Last auf dem NAS.

Bewusst ohne FastAPI-Abhängigkeit: dieser Service wirft eigene Fehler, die
Aufrufer selbst abbilden. HTTPException hier wäre im PRTG-Pfad falsch - dort
gehören Probleme als `prtg.error` in den Antwortkörper, nicht in den
HTTP-Status (siehe app/api/prtg_routes.py).
"""
import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from app.services.jobs_store import jobs_store
from app.services.security import SecretDecryptionError

logger = logging.getLogger(__name__)

LOGIN_TIMEOUT = 15  # Sekunden
SESSION_TTL = 300  # Sekunden (5 Minuten)

# Session-Cache: {connection_id: (SynologyAPI-Instanz, expires_at)}
_session_cache: Dict[int, Tuple[Any, float]] = {}
# Metrik-Abfragen laufen im Worker-Thread, Browse-Requests im Event-Loop -
# ohne Lock ist "prüfen, dann zugreifen" auf dem Dict nicht sicher
# (siehe test_metrics_concurrency.py).
_cache_lock = threading.Lock()


class NASSessionError(Exception):
    """Basisklasse: Session konnte nicht hergestellt werden"""


class NASConnectionNotFound(NASSessionError):
    """Die NAS-Verbindung existiert nicht"""


class NASCredentialsError(NASSessionError):
    """Gespeicherte Zugangsdaten sind unbrauchbar (Key rotiert o.ä.)"""


class NASLoginFailed(NASSessionError):
    """Anmeldung am NAS fehlgeschlagen"""


class NASUnreachable(NASSessionError):
    """NAS nicht erreichbar (Timeout, Netzwerkfehler)"""


def make_api(
    host: str, port: Optional[int], use_https: bool, verify_ssl: bool
) -> Any:
    """Erzeugt eine SynologyAPI-Instanz ohne Rate-Limit (interaktive Nutzung)"""
    from explore_syno_api import SynologyAPI

    return SynologyAPI(
        host,
        port=port,
        use_https=use_https,
        rate_limit_delay=0,
        output_json=True,
        verify_ssl=verify_ssl,
    )


def evict_session(connection_id: int) -> None:
    """Entfernt eine gecachte Session (bei Update/Delete der Verbindung)"""
    with _cache_lock:
        _session_cache.pop(connection_id, None)


def clear_sessions() -> None:
    """Leert den gesamten Cache (für Tests)"""
    with _cache_lock:
        _session_cache.clear()


async def get_session(connection_id: int) -> Any:
    """
    Liefert eine eingeloggte SynologyAPI-Instanz (aus dem Cache oder per Login).

    Raises:
        NASConnectionNotFound, NASCredentialsError, NASLoginFailed, NASUnreachable
    """
    with _cache_lock:
        cached = _session_cache.get(connection_id)
        if cached is not None:
            api, expires_at = cached
            if expires_at > time.time():
                return api
            _session_cache.pop(connection_id, None)

    row = jobs_store.get_connection_row(connection_id)
    if row is None:
        raise NASConnectionNotFound(
            f"NAS-Verbindung {connection_id} nicht gefunden"
        )
    try:
        password = jobs_store.get_connection_password(connection_id)
    except SecretDecryptionError as e:
        raise NASCredentialsError(str(e)) from e

    api = make_api(
        row["host"], row["port"], bool(row["use_https"]), bool(row["verify_ssl"])
    )
    try:
        success = await asyncio.wait_for(
            asyncio.to_thread(api.login, row["username"], password),
            timeout=LOGIN_TIMEOUT,
        )
    except asyncio.TimeoutError as e:
        raise NASUnreachable(
            "Zeitüberschreitung beim Verbinden mit dem NAS"
        ) from e
    except Exception as e:
        raise NASUnreachable(f"Verbindung zum NAS fehlgeschlagen: {e}") from e

    if not success:
        raise NASLoginFailed(
            "Anmeldung am NAS fehlgeschlagen - bitte Zugangsdaten prüfen"
        )

    with _cache_lock:
        _session_cache[connection_id] = (api, time.time() + SESSION_TTL)
    return api
