"""FastAPI Main Application"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from dotenv import load_dotenv

# .env laden, bevor App-Module Umgebungsvariablen lesen
# (SSA_ADMIN_PASSWORD, SSA_SECRET_KEY, ...). Bereits gesetzte
# Umgebungsvariablen haben Vorrang vor der .env.
load_dotenv()

from fastapi import Depends

from app.api.routes import router
from app.api.auth_routes import router as auth_router
from app.api.nas_routes import router as nas_router
from app.api.job_routes import router as job_router
from app.api.token_routes import router as token_router
from app.api.prtg_routes import router as prtg_router
from app.api.deps import require_auth
from app.services.scheduler import scheduler_service
from app.services.storage import storage, get_storage
from app.services.scanner import scanner_service
from app.services.jobs_store import initialize_jobs_store, jobs_store
from app.services.security import admin_password_configured
from app.services.health import collect_health, mark_server_start

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan-Event-Handler für Startup und Shutdown
    """
    # Startup
    mark_server_start()
    logger.info("Starte FastAPI Server...")
    
    if not admin_password_configured():
        logger.warning(
            "=" * 60 + "\n"
            "WARNUNG: SSA_ADMIN_PASSWORD ist nicht gesetzt!\n"
            "Der Login ist deaktiviert, bis die Umgebungsvariable gesetzt\n"
            "und der Server neu gestartet wurde.\n" + "=" * 60
        )

    try:
        # Initialisiere Jobs-Store (gleiche DB wie die Scan-Historie)
        # und importiere config.yaml-Scans einmalig
        initialize_jobs_store(get_storage().db_path)
        import_result = jobs_store.import_from_config_yaml()
        if import_result.get("imported"):
            logger.info(
                f"config.yaml importiert: {import_result['jobs']} Job(s), "
                f"{import_result['connections']} NAS-Verbindung(en)"
            )
    except Exception as e:
        logger.error(f"Fehler beim Initialisieren des Jobs-Stores: {e}")

    try:
        # Lade Jobs aus der Datenbank und starte Scheduler
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
# Origins konfigurierbar via SSA_CORS_ORIGINS (kommasepariert).
# Default: Vite-Dev-Server. In Produktion serviert das Backend das Frontend
# same-origin, dann ist CORS ohnehin nicht nötig.
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("SSA_CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,  # Bearer-Token im Header, keine Cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
# Auth-Endpoints sind offen (Login), alle anderen erfordern ein gültiges Token
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(
    router, prefix="/api", tags=["scans"], dependencies=[Depends(require_auth)]
)
app.include_router(
    nas_router,
    prefix="/api/nas-connections",
    tags=["nas-connections"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    job_router,
    prefix="/api/scan-jobs",
    tags=["scan-jobs"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    token_router,
    prefix="/api/api-tokens",
    tags=["api-tokens"],
    dependencies=[Depends(require_auth)],
)
# PRTG-Sensor-Endpoints (read-only, auch für Monitoring-API-Tokens erreichbar)
app.include_router(
    prtg_router,
    prefix="/api/prtg",
    tags=["prtg"],
    dependencies=[Depends(require_auth)],
)

# WICHTIG: /health muss VOR der SPA-Catch-all-Route registriert werden,
# sonst verschattet /{full_path:path} den Endpoint (Starlette matcht in Reihenfolge).
@app.get("/health")
async def health_check():
    """
    Erweiterter Health-Check Endpoint mit Systemdaten.

    Die Daten kommen aus app/services/health.py - dieselbe Quelle nutzen
    die PRTG-Sensor-Endpoints unter /api/prtg.
    """
    return collect_health()


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True  # Nur für Entwicklung
    )
