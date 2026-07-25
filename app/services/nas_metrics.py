"""Sammlung der NAS-Systemmetriken (Kapazität via File Station, Health via SNMP).

Aufbau wie app/services/health.py: die collect_*-Funktionen liefern rohe
Dicts, die Formatierung (JSON-Antwort bzw. PRTG-Kanäle) passiert erst in den
Routes. So sehen der generische Endpoint und die PRTG-Sensoren dieselben Werte.

Es wird nichts persistiert: die Werte werden live geholt und nur kurz
zwischengespeichert. Zeitreihen führen die Monitoring-Systeme selbst.
"""
import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.jobs_store import jobs_store
from app.services.nas_session import (
    NASSessionError,
    evict_session,
    get_session,
)

logger = logging.getLogger(__name__)

LIST_TIMEOUT = 20  # Sekunden
# Kurzer Cache, damit Capacity- und Health-Sensor desselben NAS sich einen
# Abruf teilen: PRTG pollt je Sensor (Default 60 s) unabhängig voneinander.
CACHE_TTL = 60.0

_cache: Dict[Tuple[int, str], Tuple[Any, float]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    """Leert den Metrik-Cache (für Tests und nach Verbindungsänderungen)"""
    with _cache_lock:
        _cache.clear()


async def _cached(
    key: Tuple[int, str], producer: Callable[[], Any]
) -> Tuple[Any, bool]:
    """
    Liefert (Wert, aus_dem_Cache) und ruft `producer` nur bei kaltem Cache.

    Fehler werden nicht gecacht - ein kurzzeitig nicht erreichbares NAS soll
    sich beim nächsten Poll sofort wieder erholen können.
    """
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None:
            value, expires_at = entry
            if expires_at > now:
                return value, True
            _cache.pop(key, None)

    value = await producer()

    with _cache_lock:
        _cache[key] = (value, time.time() + CACHE_TTL)
    return value, False


# ----------------------------------------------------------------------
# Kapazität (File Station)
# ----------------------------------------------------------------------

def _volume_name(real_path: str) -> Optional[str]:
    """
    Volume-Name aus dem real_path einer Freigabe ("/volume1/video" -> "volume1").
    """
    parts = [part for part in (real_path or "").split("/") if part]
    return parts[0] if parts else None


def parse_shares(shares: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Wertet die Antwort von list_share zu Kapazitätsmetriken aus.

    Mehrere Freigaben liegen in aller Regel auf demselben Volume und melden
    dann identische freespace/totalspace-Werte. Ohne Deduplizierung über den
    real_path würde derselbe Speicher mehrfach gezählt - bei fünf Shares auf
    /volume1 also die fünffache Kapazität.

    Als Sprache dieser Funktion sind reine Dicts gewählt (kein NAS-Zugriff),
    damit sie ohne Netzwerk testbar bleibt.
    """
    volumes: Dict[str, Dict[str, Any]] = {}
    share_count = 0
    shares_without_write = 0
    virtual_mounts = 0

    # Alphabetisch, damit die Zuordnung bei fehlendem real_path deterministisch
    # bleibt - PRTG identifiziert Kanäle über ihren Namen.
    for share in sorted(shares, key=lambda s: str(s.get("name") or "")):
        share_count += 1
        additional = share.get("additional") or {}

        perm = additional.get("perm")
        if isinstance(perm, dict) and perm.get("write") is False:
            shares_without_write += 1

        if additional.get("mount_point_type"):
            virtual_mounts += 1

        status = additional.get("volume_status")
        if not isinstance(status, dict):
            continue
        total = status.get("totalspace")
        free = status.get("freespace")
        if total is None or free is None:
            continue

        try:
            total = int(total)
            free = int(free)
        except (TypeError, ValueError):
            continue

        name = _volume_name(additional.get("real_path", ""))
        if name is None:
            # Ohne real_path bleibt nur die Kapazität als Identität. Der
            # Anzeigename kommt vom ersten (alphabetisch) beitragenden Share.
            key = f"{total}:{free}"
            name = str(share.get("name") or "unbekannt")
        else:
            key = name

        entry = volumes.get(key)
        if entry is None:
            volumes[key] = {
                "name": name,
                "total_bytes": total,
                "free_bytes": free,
                "used_bytes": max(total - free, 0),
                "used_percent": round((total - free) / total * 100, 1) if total else 0.0,
                "readonly": bool(status.get("readonly")),
                "share_count": 1,
            }
        else:
            entry["share_count"] += 1
            # readonly ist eine Volume-Eigenschaft; meldet es irgendeine
            # Freigabe, gilt es für das Volume.
            entry["readonly"] = entry["readonly"] or bool(status.get("readonly"))

    return {
        "volumes": sorted(volumes.values(), key=lambda v: v["name"]),
        "share_count": share_count,
        "shares_without_write": shares_without_write,
        "virtual_mounts": virtual_mounts,
    }


async def _fetch_shares(connection_id: int) -> List[Dict[str, Any]]:
    """
    Holt die Freigabenliste inkl. volume_status.

    list_shared_folders fordert volume_status bereits an (siehe
    explore_syno_api.py) - für die Kapazitätswerte fällt also kein
    zusätzlicher Aufruf am NAS an.
    """

    def _call(api):
        return api.list_shared_folders(show_message=False)

    api = await get_session(connection_id)
    shares = await asyncio.wait_for(
        asyncio.to_thread(_call, api), timeout=LIST_TIMEOUT
    )
    if shares is None:
        # Vermutlich abgelaufene Session: einmal frisch anmelden und erneut
        # versuchen (gleiches Muster wie beim Verzeichnis-Browsing).
        evict_session(connection_id)
        api = await get_session(connection_id)
        shares = await asyncio.wait_for(
            asyncio.to_thread(_call, api), timeout=LIST_TIMEOUT
        )
    if shares is None:
        raise NASSessionError("Freigaben konnten nicht gelesen werden")
    return shares


async def collect_capacity(connection_id: int) -> Tuple[Dict[str, Any], bool]:
    """
    Kapazitätsmetriken eines NAS. Liefert (Daten, aus_dem_Cache).

    Raises:
        NASSessionError und Subklassen, asyncio.TimeoutError
    """

    async def produce() -> Dict[str, Any]:
        started = time.monotonic()
        shares = await _fetch_shares(connection_id)
        metrics = parse_shares(shares)
        metrics["response_seconds"] = round(time.monotonic() - started, 3)
        return metrics

    return await _cached((connection_id, "capacity"), produce)


# ----------------------------------------------------------------------
# Systemgesundheit (SNMP)
# ----------------------------------------------------------------------

class SNMPNotConfigured(Exception):
    """Für diese Verbindung ist kein SNMP-Zugang hinterlegt"""


async def collect_health(connection_id: int) -> Tuple[Dict[str, Any], bool]:
    """
    Systemmetriken eines NAS über SNMP. Liefert (Daten, aus_dem_Cache).

    Raises:
        SNMPNotConfigured, SNMPError
    """
    # Lazy-Import: pysnmp wird nur gebraucht, wenn SNMP auch konfiguriert ist.
    from app.services.snmp_client import collect_snmp_health

    config = jobs_store.get_snmp_config(connection_id)
    if config is None:
        raise SNMPNotConfigured(
            "SNMP ist für diese NAS-Verbindung nicht aktiviert"
        )

    async def produce() -> Dict[str, Any]:
        started = time.monotonic()
        metrics = await collect_snmp_health(config)
        metrics["response_seconds"] = round(time.monotonic() - started, 3)
        return metrics

    return await _cached((connection_id, "health"), produce)


# ----------------------------------------------------------------------
# Fassade für die Endpoints
# ----------------------------------------------------------------------

def _source_error(exc: Exception) -> Dict[str, Any]:
    return {"available": False, "error": str(exc), "data": None}


async def collect_metrics(
    connection: Dict[str, Any], groups: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Alle angeforderten Metriken einer Verbindung, je Quelle einzeln abgesichert.

    Eine ausgefallene Quelle darf die andere nie mitreißen: ein NAS ohne
    SNMP liefert weiterhin vollständige Kapazitätswerte.
    """
    connection_id = connection["id"]
    wanted = set(groups) if groups else {"capacity", "health"}
    sources: Dict[str, Any] = {}
    any_cached = False

    if "capacity" in wanted:
        try:
            data, cached = await collect_capacity(connection_id)
            sources["filestation"] = {"available": True, "error": None, "data": data}
            any_cached = any_cached or cached
        except asyncio.TimeoutError:
            sources["filestation"] = _source_error(
                Exception("Zeitüberschreitung beim Abruf der Freigaben")
            )
        except Exception as e:
            logger.warning(
                f"Kapazitätsmetriken für Verbindung {connection_id} fehlgeschlagen: {e}"
            )
            sources["filestation"] = _source_error(e)

    if "health" in wanted:
        try:
            data, cached = await collect_health(connection_id)
            sources["snmp"] = {"available": True, "error": None, "data": data}
            any_cached = any_cached or cached
        except SNMPNotConfigured as e:
            sources["snmp"] = _source_error(e)
        except asyncio.TimeoutError:
            sources["snmp"] = _source_error(
                Exception("Zeitüberschreitung bei der SNMP-Abfrage")
            )
        except Exception as e:
            logger.warning(
                f"SNMP-Metriken für Verbindung {connection_id} fehlgeschlagen: {e}"
            )
            sources["snmp"] = _source_error(e)

    return {
        "connection_id": connection_id,
        "name": connection["name"],
        "host": connection["host"],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "cached": any_cached,
        "sources": sources,
    }
