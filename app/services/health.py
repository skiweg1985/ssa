"""Sammlung der Health-/System-Metriken.

Gemeinsame Quelle für den offenen /health-Endpoint und die PRTG-Sensor-Endpoints,
damit beide dieselben Werte sehen und psutil nur an einer Stelle abgefragt wird.
"""
import logging
import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# psutil ist optional (Systemressourcen). Als Modul-Global gehalten,
# damit Tests es per monkeypatch abschalten können.
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover - abhängig von der Installation
    psutil = None
    PSUTIL_AVAILABLE = False

SERVER_VERSION = "1.0.0"

_server_start_time: Optional[datetime] = None


# ----------------------------------------------------------------------
# Uptime
# ----------------------------------------------------------------------

def mark_server_start() -> None:
    """Merkt sich den Startzeitpunkt (wird im Lifespan aufgerufen)"""
    global _server_start_time
    _server_start_time = datetime.now(timezone.utc)


def get_server_start_time() -> Optional[datetime]:
    return _server_start_time


def get_uptime_seconds() -> Optional[float]:
    """Laufzeit des Servers in Sekunden, None wenn der Start nicht erfasst wurde"""
    if _server_start_time is None:
        return None
    return (datetime.now(timezone.utc) - _server_start_time).total_seconds()


def format_uptime(uptime_seconds: float) -> str:
    """Formatiert Sekunden als '3d 4h 12m'"""
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"


# ----------------------------------------------------------------------
# Systemressourcen
# ----------------------------------------------------------------------

def collect_system_raw() -> Optional[Dict[str, Any]]:
    """
    Rohe Systemwerte (unformatiert, für PRTG-Kanäle).

    Returns:
        Dict mit cpu_percent, cpu_count, load_average, mem_* und disk_*,
        oder None wenn psutil nicht verfügbar ist bzw. die Abfrage fehlschlägt.
    """
    if not PSUTIL_AVAILABLE:
        return None
    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "cpu_count": psutil.cpu_count(),
            "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
            "mem_total": memory.total,
            "mem_available": memory.available,
            "mem_used": memory.used,
            "mem_percent": memory.percent,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_free": disk.free,
            "disk_percent": disk.percent,
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Systemressourcen: {e}")
        return None


def collect_system_metrics() -> Dict[str, Any]:
    """Systemressourcen im /health-Format (unverändertes Antwortschema)"""
    if not PSUTIL_AVAILABLE:
        return {"available": False, "note": "psutil nicht installiert"}

    raw = collect_system_raw()
    if raw is None:
        return {"error": "Systemressourcen konnten nicht abgerufen werden"}

    return {
        "cpu": {
            "percent": raw["cpu_percent"],
            "count": raw["cpu_count"],
            "load_average": raw["load_average"],
        },
        "memory": {
            "total_gb": round(raw["mem_total"] / (1024**3), 2),
            "available_gb": round(raw["mem_available"] / (1024**3), 2),
            "used_gb": round(raw["mem_used"] / (1024**3), 2),
            "percent": raw["mem_percent"],
        },
        "disk": {
            "total_gb": round(raw["disk_total"] / (1024**3), 2),
            "used_gb": round(raw["disk_used"] / (1024**3), 2),
            "free_gb": round(raw["disk_free"] / (1024**3), 2),
            "percent": raw["disk_percent"],
        },
    }


# ----------------------------------------------------------------------
# Scheduler / Storage / Scans
# ----------------------------------------------------------------------

def collect_scheduler_metrics() -> Dict[str, Any]:
    """Generische Scheduler-Statistiken (keine Job-Details)"""
    from app.services.scheduler import scheduler_service

    try:
        running = (
            scheduler_service.scheduler.running if scheduler_service.scheduler else False
        )
        all_jobs = scheduler_service.get_all_jobs()
        enabled_jobs = [j for j in all_jobs.values() if j.get("next_run") is not None]
        return {
            "running": running,
            "total_jobs": len(all_jobs),
            "enabled_jobs": len(enabled_jobs),
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Scheduler-Informationen: {e}")
        return {"error": str(e)}


def collect_storage_metrics() -> Dict[str, Any]:
    """Storage-Kennzahlen im /health-Format"""
    from app.services.storage import storage

    try:
        stats = storage.get_storage_stats()
        return {
            "scan_count": stats.get("scan_count", 0),
            "nas_count": stats.get("nas_count", 0),
            "folder_count": stats.get("folder_count", 0),
            "total_results_db": stats.get("total_results_db", 0),
            "db_size_mb": round(stats.get("db_size_mb", 0), 2),
            "db_path": stats.get("db_path", "unknown"),
            "oldest_entry": stats.get("oldest_entry"),
            "newest_entry": stats.get("newest_entry"),
            "auto_cleanup_enabled": stats.get("auto_cleanup_enabled", False),
            "auto_cleanup_days": stats.get("auto_cleanup_days", 90),
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Storage-Statistiken: {e}")
        return {"error": str(e)}


def collect_scan_metrics() -> Dict[str, Any]:
    """Scan-Zähler im /health-Format"""
    from app.services.jobs_store import jobs_store
    from app.services.scanner import scanner_service

    try:
        jobs = jobs_store.list_jobs()
        running_scans = [
            job["name"] for job in jobs if scanner_service.is_scan_running(job["slug"])
        ]
        return {
            "total_configured": len(jobs),
            "enabled": len([j for j in jobs if j["enabled"]]),
            "running": len(running_scans),
            "running_scans": running_scans,
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Scan-Informationen: {e}")
        return {"error": str(e)}


def collect_job_health() -> Dict[str, Any]:
    """
    Aggregierter Job-Zustand für die PRTG-Server-Kanäle.

    Returns:
        total, enabled, running, failed (letzter Lauf fehlgeschlagen),
        without_results (noch nie gelaufen), stalest_seconds/stalest_slug
        (ältester letzter Lauf über alle aktivierten Jobs).
    """
    from app.services.jobs_store import jobs_store
    from app.services.scanner import scanner_service
    from app.services.storage import storage

    result = {
        "total": 0,
        "enabled": 0,
        "running": 0,
        "failed": 0,
        "without_results": 0,
        "stalest_seconds": None,
        "stalest_slug": None,
    }
    try:
        now = datetime.now(timezone.utc)
        jobs = jobs_store.list_jobs()
        result["total"] = len(jobs)

        for job in jobs:
            slug = job["slug"]
            if job["enabled"]:
                result["enabled"] += 1
            if scanner_service.is_scan_running(slug):
                result["running"] += 1

            latest = storage.get_latest_result(slug)
            if latest is None:
                result["without_results"] += 1
                continue
            if latest.status == "failed":
                result["failed"] += 1

            # Ältester letzter Lauf (nur aktivierte Jobs - deaktivierte laufen bewusst nicht)
            if job["enabled"]:
                timestamp = latest.timestamp
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                age = (now - timestamp).total_seconds()
                if result["stalest_seconds"] is None or age > result["stalest_seconds"]:
                    result["stalest_seconds"] = age
                    result["stalest_slug"] = slug
    except Exception as e:
        logger.warning(f"Fehler beim Ermitteln des Job-Zustands: {e}")
    return result


def collect_config_warnings() -> List[Dict[str, str]]:
    """
    Konfigurationswarnungen.

    Lieferte früher die Duplikat-Warnungen des config.yaml-Loaders. Seit Jobs
    ausschliesslich im Jobs-Store leben, gibt es keine Quelle mehr dafür - die
    Funktion bleibt als Anschluss erhalten, weil /health, der PRTG-Sensor und
    der Monitor-State CONFIG_WARNINGS darauf aufsetzen.
    """
    return []


# ----------------------------------------------------------------------
# Gesamt-Health (Antwort des /health-Endpoints)
# ----------------------------------------------------------------------

def collect_health() -> Dict[str, Any]:
    """
    Vollständige Health-Daten.

    WICHTIG: Struktur ist der öffentliche Vertrag von GET /health und darf
    sich nicht ändern (siehe test_health_contract in tests/test_prtg_api.py).
    """
    health_data: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": {
            "version": SERVER_VERSION,
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "platform_version": platform.version(),
        },
    }

    uptime_seconds = get_uptime_seconds()
    if uptime_seconds is not None:
        health_data["server"]["uptime_seconds"] = int(uptime_seconds)
        health_data["server"]["uptime_formatted"] = format_uptime(uptime_seconds)
        start_time = get_server_start_time()
        if start_time is not None:
            health_data["server"]["start_time"] = start_time.isoformat()

    health_data["system"] = collect_system_metrics()
    health_data["scheduler"] = collect_scheduler_metrics()
    health_data["storage"] = collect_storage_metrics()
    health_data["scans"] = collect_scan_metrics()

    warnings = collect_config_warnings()
    if warnings:
        health_data["warnings"] = warnings
        health_data["status"] = "warning"

    return health_data
