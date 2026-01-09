"""FastAPI Main Application"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.api.routes import router
from app.services.scheduler import scheduler_service

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


# HTML-Formular Route
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Gibt das HTML-Formular für Status und Ergebnisse zurück
    """
    try:
        templates_dir = Path(__file__).parent / "templates"
        index_file = templates_dir / "index.html"
        
        if not index_file.exists():
            logger.error(f"index.html nicht gefunden in: {index_file}")
            return HTMLResponse(
                content="<h1>Fehler: index.html nicht gefunden</h1>",
                status_code=500
            )
        
        with open(index_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.exception(f"Fehler beim Laden des HTML-Formulars: {e}")
        return HTMLResponse(
            content=f"<h1>Fehler beim Laden des Formulars: {str(e)}</h1>",
            status_code=500
        )


@app.get("/health")
async def health_check():
    """
    Health-Check Endpoint
    """
    return {
        "status": "healthy",
        "scheduler_running": scheduler_service.scheduler.running if scheduler_service.scheduler else False
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Nur für Entwicklung
    )
