"""API-Routes für die Scan-Job-Verwaltung (CRUD mit sofortigem Scheduler-Sync)"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.models.admin import ScanJobCreate, ScanJobPublic, ScanJobUpdate
from app.models.config import NASConfigYAML, ScanTaskConfigYAML
from app.services.jobs_store import NotFoundError, jobs_store
from app.services.scheduler import scheduler_service
from app.services.storage import storage

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_job_payload(payload: ScanJobCreate) -> None:
    """
    Validiert einen Job-Payload VOR der Persistierung:

    - Pfad-Kombinationsregeln über den bestehenden ScanTaskConfigYAML-Validator
    - Intervall über dieselbe Logik, die auch der Scheduler nutzt
    - Existenz der NAS-Verbindung
    """
    connection = jobs_store.get_connection(payload.nas_connection_id)
    if connection is None:
        raise HTTPException(
            status_code=422,
            detail=f"NAS-Verbindung {payload.nas_connection_id} existiert nicht",
        )

    # Probe-Konstruktion: nutzt den Validator aus app/models/config.py
    # (Dummy-Passwort, das echte wird hier nicht gebraucht)
    try:
        ScanTaskConfigYAML(
            name=payload.name,
            nas=NASConfigYAML(
                host=connection["host"],
                username=connection["username"],
                password="dummy",
                port=connection["port"],
                use_https=connection["use_https"],
                verify_ssl=connection["verify_ssl"],
            ),
            shares=payload.shares,
            folders=payload.folders,
            paths=payload.paths,
            interval=payload.interval,
            enabled=payload.enabled,
        )
    except ValidationError as e:
        messages = "; ".join(err.get("msg", "") for err in e.errors())
        raise HTTPException(
            status_code=422,
            detail=f"Ungültige Job-Konfiguration: {messages}",
        )

    # Intervall: exakt dieselbe Logik wie beim Schedulen
    if scheduler_service._create_trigger(payload.interval, payload.name) is None:
        raise HTTPException(
            status_code=422,
            detail="Ungültiges Intervall (z.B. '30m' oder Cron '0 3 * * *')",
        )


def _sync_scheduler(job: dict) -> None:
    """Synct einen Job-Datensatz in den Scheduler (add/re-add/remove)"""
    slug = job["slug"]
    scheduler_service.remove_scan_job(slug)
    if job["enabled"]:
        scan_config = jobs_store.to_scan_config(job)
        scheduler_service.add_scan_job(scan_config)


@router.get("", response_model=list[ScanJobPublic])
async def list_jobs():
    """Alle Scan-Jobs (Rohansicht für die Verwaltung)"""
    return jobs_store.list_jobs()


@router.post("", response_model=ScanJobPublic, status_code=201)
async def create_job(request: ScanJobCreate):
    """Neuen Scan-Job anlegen und sofort im Scheduler registrieren"""
    _validate_job_payload(request)
    job = jobs_store.create_job(
        name=request.name,
        nas_connection_id=request.nas_connection_id,
        interval=request.interval,
        enabled=request.enabled,
        shares=request.shares,
        folders=request.folders,
        paths=request.paths,
    )
    try:
        _sync_scheduler(job)
    except Exception as e:
        logger.error(f"Scheduler-Sync für neuen Job '{job['slug']}' fehlgeschlagen: {e}")
    return job


@router.put("/{slug}", response_model=ScanJobPublic)
async def update_job(slug: str, request: ScanJobUpdate):
    """Scan-Job aktualisieren (Slug bleibt unverändert, Historie bleibt intakt)"""
    _validate_job_payload(request)
    try:
        job = jobs_store.update_job(
            slug,
            name=request.name,
            nas_connection_id=request.nas_connection_id,
            interval=request.interval,
            enabled=request.enabled,
            shares=request.shares,
            folders=request.folders,
            paths=request.paths,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        _sync_scheduler(job)
    except Exception as e:
        logger.error(f"Scheduler-Sync für Job '{slug}' fehlgeschlagen: {e}")
    return job


@router.delete("/{slug}", status_code=204)
async def delete_job(slug: str, delete_history: bool = False):
    """
    Scan-Job löschen und aus dem Scheduler entfernen.

    Mit delete_history=true wird auch die Scan-Historie des Jobs gelöscht.
    """
    try:
        jobs_store.delete_job(slug)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    scheduler_service.remove_scan_job(slug)

    if delete_history:
        try:
            storage.clear_results(scan_slug=slug)
        except Exception as e:
            logger.warning(
                f"Historie für gelöschten Job '{slug}' konnte nicht entfernt werden: {e}"
            )
