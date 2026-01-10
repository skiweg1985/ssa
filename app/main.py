"""FastAPI Main Application"""
import logging
import os
import sys
import platform
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# Versuche psutil zu importieren (optional für Systemressourcen)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from app.api.routes import router
from app.services.scheduler import scheduler_service
from app.services.storage import storage
from app.services.scanner import scanner_service
from app.config.loader import load_config

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Aktiviere Logging für explore_syno_api (damit Job-Logs sichtbar sind)
# Setze Umgebungsvariable, damit explore_syno_api auch loggt
os.environ.setdefault('SYNO_ENABLE_LOGS', 'info')

# Konfiguriere Logger für explore_syno_api explizit
explore_logger = logging.getLogger('explore_syno_api')
explore_logger.setLevel(logging.INFO)
# Entferne separate Handler, damit alles über das Root-Logging geht
if explore_logger.handlers:
    for handler in explore_logger.handlers[:]:
        explore_logger.removeHandler(handler)

# Server-Startzeitpunkt für Uptime-Berechnung
_server_start_time = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan-Event-Handler für Startup und Shutdown
    """
    global _server_start_time
    # Startup
    _server_start_time = datetime.now(timezone.utc)
    logger.info("Starte FastAPI Server...")
    
    try:
        # Lade Konfiguration und starte Scheduler
        # Storage wird automatisch im Projekt-Root initialisiert (history.db)
        scheduler_service.load_and_schedule()
        scheduler_service.start()
        logger.info("Scheduler gestartet")
    except Exception as e:
        logger.error(f"Fehler beim Starten des Schedulers: {e}")
        # Server startet trotzdem, aber ohne automatische Scans
    
    yield
    
    # Shutdown
    logger.info("Stoppe FastAPI Server...")
    scheduler_service.stop()
    logger.info("Scheduler gestoppt")


# Erstelle FastAPI App
app = FastAPI(
    title="Synology Space Analyzer API",
    description="REST API für Synology Space Analyzer mit automatischem Scheduling",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In Produktion sollte dies eingeschränkt werden
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(router, prefix="/api", tags=["scans"])

# Frontend build directory (React app)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    # Mount assets directory
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # Serve index.html for root and all non-API routes
    from fastapi.responses import FileResponse
    
    @app.get("/", response_class=HTMLResponse)
    async def serve_frontend_root():
        """Serve React frontend index.html"""
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        logger.error(f"React frontend index.html nicht gefunden in: {index_file}")
        return HTMLResponse(
            content="<h1>Fehler: React Frontend nicht gefunden. Bitte 'npm run build' im frontend/ Verzeichnis ausführen.</h1>",
            status_code=500
        )
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """
        Serve the React frontend for all non-API routes.
        """
        # Don't interfere with API routes or health endpoint
        if full_path.startswith("api/") or full_path == "health":
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        
        # Try to serve static file first (for assets, etc.)
        static_file = frontend_dist / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        
        # Otherwise serve index.html (for React Router)
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        
        # Frontend not found
        logger.error(f"React frontend index.html nicht gefunden in: {index_file}")
        return HTMLResponse(
            content="<h1>Fehler: React Frontend nicht gefunden. Bitte 'npm run build' im frontend/ Verzeichnis ausführen.</h1>",
            status_code=500
        )
else:
    # Frontend build not found
    @app.get("/", response_class=HTMLResponse)
    async def read_root():
        logger.error(f"React frontend build nicht gefunden in: {frontend_dist}")
        return HTMLResponse(
            content="<h1>Fehler: React Frontend Build nicht gefunden</h1><p>Bitte 'npm run build' im frontend/ Verzeichnis ausführen.</p>",
            status_code=500
        )


@app.get("/health")
async def health_check():
    """
    Erweiterter Health-Check Endpoint mit Systemdaten
    """
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": {
            "version": "1.0.0",
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "platform_version": platform.version(),
        }
    }
    
    # Server-Uptime
    if _server_start_time:
        uptime_seconds = (datetime.now(timezone.utc) - _server_start_time).total_seconds()
        uptime_days = uptime_seconds // 86400
        uptime_hours = (uptime_seconds % 86400) // 3600
        uptime_minutes = (uptime_seconds % 3600) // 60
        health_data["server"]["uptime_seconds"] = int(uptime_seconds)
        health_data["server"]["uptime_formatted"] = f"{int(uptime_days)}d {int(uptime_hours)}h {int(uptime_minutes)}m"
        health_data["server"]["start_time"] = _server_start_time.isoformat()
    
    # Systemressourcen (wenn psutil verfügbar)
    if PSUTIL_AVAILABLE:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            health_data["system"] = {
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "percent": memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent": disk.percent
                }
            }
        except Exception as e:
            logger.warning(f"Fehler beim Abrufen der Systemressourcen: {e}")
            health_data["system"] = {"error": str(e)}
    else:
        health_data["system"] = {"available": False, "note": "psutil nicht installiert"}
    
    # Scheduler-Informationen (nur generische Statistiken, keine Job-Details)
    try:
        scheduler_running = scheduler_service.scheduler.running if scheduler_service.scheduler else False
        all_jobs = scheduler_service.get_all_jobs()
        enabled_jobs = [job for job in all_jobs.values() if job.get("next_run") is not None]
        
        health_data["scheduler"] = {
            "running": scheduler_running,
            "total_jobs": len(all_jobs),
            "enabled_jobs": len(enabled_jobs)
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Scheduler-Informationen: {e}")
        health_data["scheduler"] = {"error": str(e)}
    
    # Storage-Statistiken
    try:
        storage_stats = storage.get_storage_stats()
        health_data["storage"] = {
            "scan_count": storage_stats.get("scan_count", 0),
            "nas_count": storage_stats.get("nas_count", 0),
            "folder_count": storage_stats.get("folder_count", 0),
            "total_results_db": storage_stats.get("total_results_db", 0),
            "db_size_mb": round(storage_stats.get("db_size_mb", 0), 2),
            "db_path": storage_stats.get("db_path", "unknown"),
            "oldest_entry": storage_stats.get("oldest_entry"),
            "newest_entry": storage_stats.get("newest_entry"),
            "auto_cleanup_enabled": storage_stats.get("auto_cleanup_enabled", False),
            "auto_cleanup_days": storage_stats.get("auto_cleanup_days", 90)
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Storage-Statistiken: {e}")
        health_data["storage"] = {"error": str(e)}
    
    # Anzahl laufender Scans
    try:
        config = load_config()
        running_scans = []
        for scan_config in config.scans:
            if scanner_service.is_scan_running(scan_config.name):
                running_scans.append(scan_config.name)
        
        health_data["scans"] = {
            "total_configured": len(config.scans),
            "enabled": len([s for s in config.scans if s.enabled]),
            "running": len(running_scans),
            "running_scans": running_scans
        }
    except Exception as e:
        logger.warning(f"Fehler beim Abrufen der Scan-Informationen: {e}")
        health_data["scans"] = {"error": str(e)}
    
    return health_data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True  # Nur für Entwicklung
    )
