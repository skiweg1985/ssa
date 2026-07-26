"""API Routes für FastAPI"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Response
from typing import List, Optional
from urllib.parse import quote
from datetime import datetime

from app.models.scan import (
    ScanResult,
    ScanStatus,
    ScanListResponse,
    TriggerResponse,
    CancelResponse,
    ScanHistoryResponse,
    NASConfigPublic
)
from app.services.storage import storage
from app.services.scanner import scanner_service
from app.services.scheduler import scheduler_service
from app.services.jobs_store import jobs_store
from app.services.monitoring import compute_progress_percent
from app.models.config import NASConfigYAML, ScanTaskConfigYAML

logger = logging.getLogger(__name__)

router = APIRouter()


def _job_to_view_config(job: dict) -> Optional[ScanTaskConfigYAML]:
    """
    Baut eine LESE-Ansicht eines Jobs als ScanTaskConfigYAML mit Dummy-Passwort
    (keine Entschlüsselung nötig; Passwort wird in Read-Handlern nie verwendet).
    """
    connection = jobs_store.get_connection_row(job["nas_connection_id"])
    if connection is None:
        return None
    nas = NASConfigYAML(
        host=connection["host"],
        username=connection["username"],
        password="",
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


def get_scan_config_from_db(identifier: str) -> Optional[ScanTaskConfigYAML]:
    """Lese-Ansicht eines Jobs aus der DB (Slug oder Name)"""
    job = jobs_store.get_job(identifier)
    if job is None:
        return None
    return _job_to_view_config(job)


@router.get("/scans", response_model=ScanListResponse)
async def get_scans():
    """
    Gibt eine Liste aller konfigurierten Scans mit Status zurück
    """
    try:
        scan_statuses = []

        for job in jobs_store.list_jobs():
            scan_config = _job_to_view_config(job)
            if scan_config is None:
                continue
            # Prüfe zuerst, ob Scan gerade läuft
            is_running = scanner_service.is_scan_running(scan_config.slug)
            
            # Hole letztes Ergebnis
            latest_result = storage.get_latest_result(scan_config.slug)
            
            # Hole Job-Info vom Scheduler
            job_info = scheduler_service.get_job_info(scan_config.slug)
            
            status = "pending"
            last_run = None
            next_run = None

            # WICHTIG: last_run kommt immer aus dem letzten gespeicherten Lauf -
            # auch während ein neuer Scan läuft. Sonst verlieren Monitoring-
            # Clients (und die Oberfläche) für die gesamte Laufzeit den
            # Zeitstempel des letzten Laufs.
            if latest_result:
                last_run = latest_result.timestamp

            # Wenn Scan läuft, setze Status auf "running"
            if is_running:
                status = "running"
            elif latest_result:
                status = latest_result.status

            if job_info and job_info.get("next_run"):
                next_run = job_info["next_run"]
            
            # Erstelle öffentliche NAS-Konfiguration (ohne Passwort)
            nas_config_public = None
            if scan_config.nas:
                nas_config_public = NASConfigPublic(
                    host=scan_config.nas.host,
                    username=scan_config.nas.username,
                    port=scan_config.nas.port,
                    use_https=scan_config.nas.use_https,
                    verify_ssl=scan_config.nas.verify_ssl
                )
            
            scan_status = ScanStatus(
                scan_slug=scan_config.slug,
                scan_name=scan_config.name,
                status=status,
                last_run=last_run,
                next_run=next_run,
                enabled=scan_config.enabled,
                shares=scan_config.shares,
                folders=scan_config.folders,
                paths=scan_config.paths,
                nas=nas_config_public,
                interval=scan_config.interval,
                nas_connection_id=job["nas_connection_id"]
            )
            scan_statuses.append(scan_status)
        
        return ScanListResponse(scans=scan_statuses)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Scans: {str(e)}")


@router.get("/scans/{scan_identifier}", response_model=ScanStatus)
async def get_scan(scan_identifier: str):
    """
    Gibt Details eines spezifischen Scans zurück
    Unterstützt slug oder name als Identifier
    """
    try:
        job = jobs_store.get_job(scan_identifier)
        scan_config = _job_to_view_config(job) if job else None

        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden")

        # Prüfe zuerst, ob Scan gerade läuft
        is_running = scanner_service.is_scan_running(scan_config.slug)
        
        # Hole letztes Ergebnis
        latest_result = storage.get_latest_result(scan_config.slug)
        
        # Hole Job-Info vom Scheduler
        job_info = scheduler_service.get_job_info(scan_config.slug)
        
        status = "pending"
        last_run = None
        next_run = None

        # last_run immer aus dem letzten gespeicherten Lauf (siehe get_scans)
        if latest_result:
            last_run = latest_result.timestamp

        # Wenn Scan läuft, setze Status auf "running"
        if is_running:
            status = "running"
        elif latest_result:
            status = latest_result.status

        if job_info and job_info.get("next_run"):
            next_run = job_info["next_run"]
        
        # Erstelle öffentliche NAS-Konfiguration (ohne Passwort)
        nas_config_public = None
        if scan_config.nas:
            nas_config_public = NASConfigPublic(
                host=scan_config.nas.host,
                username=scan_config.nas.username,
                port=scan_config.nas.port,
                use_https=scan_config.nas.use_https,
                verify_ssl=scan_config.nas.verify_ssl
            )
        
        return ScanStatus(
            scan_slug=scan_config.slug,
            scan_name=scan_config.name,
            status=status,
            last_run=last_run,
            next_run=next_run,
            enabled=scan_config.enabled,
            shares=scan_config.shares,
            folders=scan_config.folders,
            paths=scan_config.paths,
            nas=nas_config_public,
            interval=scan_config.interval,
            nas_connection_id=job["nas_connection_id"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden des Scans: {str(e)}")


@router.get(
    "/scans/{scan_identifier}/status",
    response_model=ScanStatus,
    deprecated=True,
)
async def get_scan_status(scan_identifier: str, response: Response):
    """
    Gibt den Status eines Scans zurück.

    VERALTET - abgelöst von `GET /api/monitor/scans/{slug}`.

    Für Monitoring ist diese Antwort schwer auszuwerten: `status` mischt
    Lebenszyklus und Ergebnis ("running" überschreibt das Ergebnis des
    vorherigen Laufs), "completed" bedeutet nicht "alle Ordner ok", es gibt
    keinen Fehlertext und keinen Zeitstempel des letzten Erfolgs, und die
    Überfälligkeit müsste der Client selbst aus `interval` errechnen.
    Der Monitoring-Endpoint liefert das alles vorberechnet als `severity`.

    Verhalten und Schema bleiben aus Kompatibilitätsgründen unverändert;
    ein Entfernungsdatum ist nicht gesetzt.
    """
    # RFC 8594: Nachfolger maschinenlesbar bekanntgeben. Bewusst ohne
    # "Sunset"-Header - es gibt keine Zusage, den Endpoint zu entfernen.
    #
    # Der Identifier darf ein Job-NAME sein, und Namen erlauben beliebiges
    # Unicode sowie Leer- und Sonderzeichen. HTTP-Header werden als Latin-1
    # kodiert - ein Emoji im Namen hätte den Endpoint sonst mit 500 beendet,
    # statt wie bisher den Status zu liefern. Deshalb percent-kodiert.
    response.headers["Deprecation"] = "true"
    successor = f"/api/monitor/scans/{quote(scan_identifier, safe='')}"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'
    return await get_scan(scan_identifier)


@router.get("/scans/{scan_identifier}/progress")
async def get_scan_progress(scan_identifier: str):
    """
    Gibt die aktuellen intermediären Status-Informationen eines laufenden Scans zurück.
    
    Args:
        scan_identifier: Slug oder Name des Scans
    
    Returns:
        Dict mit Status-Informationen (num_dir, num_file, total_size, waited, finished, current_path, progress_percent)
        oder 404 wenn Scan nicht läuft
        
        progress_percent: Prozentwert basierend auf dem letzten erfolgreichen Scan (0-100)
                         oder None wenn keine Historie vorhanden ist
    """
    try:
        scan_config = get_scan_config_from_db(scan_identifier)

        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden")

        # Prüfe ob Scan läuft
        if not scanner_service.is_scan_running(scan_config.slug):
            raise HTTPException(
                status_code=404,
                detail=f"Scan '{scan_config.name}' läuft aktuell nicht"
            )
        
        # Hole Status-Informationen
        progress = scanner_service.get_scan_progress(scan_config.slug)
        
        if not progress:
            raise HTTPException(
                status_code=404,
                detail=f"Keine Status-Informationen für Scan '{scan_config.name}' verfügbar"
            )
        
        # Fortschritt gegen den letzten erfolgreichen Lauf. Die Rechnung liegt
        # in app/services/monitoring.py, damit die Monitoring-Berichte dieselbe
        # Zahl zeigen wie diese Antwort.
        progress_percent = compute_progress_percent(
            progress, storage.get_latest_completed_result(scan_config.slug)
        )

        # Füge progress_percent zum Progress-Dict hinzu
        progress_with_percent = progress.copy()
        progress_with_percent["progress_percent"] = progress_percent
        
        # Bestimme Status basierend auf finished-Flag
        # Wenn finished=True, dann ist der Scan abgeschlossen
        if progress_with_percent.get("finished", False):
            response_status = "completed"
        else:
            response_status = "running"
        
        return {
            "scan_slug": scan_config.slug,
            "scan_name": scan_config.name,
            "status": response_status,
            "progress": progress_with_percent
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen des Status: {str(e)}")


@router.get("/scans/{scan_identifier}/results", response_model=ScanResult)
async def get_scan_results(scan_identifier: str, latest: bool = True):
    """
    Gibt die Ergebnisse eines Scans zurück
    
    Args:
        scan_identifier: Slug oder Name des Scans
        latest: Wenn True, nur das neueste Ergebnis. Wenn False, alle Ergebnisse.
    """
    try:
        scan_config = get_scan_config_from_db(scan_identifier)

        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden")

        if latest:
            result = storage.get_latest_result(scan_config.slug)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Keine Ergebnisse für Scan '{scan_config.name}' gefunden"
                )
            return result
        else:
            results = storage.get_all_results(scan_config.slug)
            if not results:
                raise HTTPException(
                    status_code=404,
                    detail=f"Keine Ergebnisse für Scan '{scan_config.name}' gefunden"
                )
            # Gibt das neueste zurück (letztes in der Liste)
            return results[-1]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Ergebnisse: {str(e)}")


@router.get("/scans/{scan_identifier}/history", response_model=ScanHistoryResponse)
async def get_scan_history(
    scan_identifier: str,
    limit: Optional[int] = Query(
        None,
        ge=1,
        description=(
            "Anzahl der gelieferten Läufe (die neuesten). "
            "Ohne Angabe wird die komplette Historie zurückgegeben."
        ),
    ),
    offset: int = Query(
        0, ge=0, description="Läufe vom neuen Ende her überspringen"
    ),
):
    """
    Gibt die Historie der Ergebnisse eines Scans zurück

    Ohne limit/offset ist das Verhalten unverändert: die komplette Historie,
    aufsteigend nach Zeitstempel. total_count nennt immer die Gesamtzahl der
    gespeicherten Läufe, unabhängig von der gelieferten Seite.

    Args:
        scan_identifier: Slug oder Name des Scans
    """
    try:
        scan_config = get_scan_config_from_db(scan_identifier)

        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden")

        total = storage.count_results(scan_config.slug)
        if not total:
            raise HTTPException(
                status_code=404,
                detail=f"Keine Ergebnisse für Scan '{scan_config.name}' gefunden"
            )

        results = storage.get_all_results(
            scan_config.slug, limit=limit, offset=offset
        )

        return ScanHistoryResponse(
            scan_slug=scan_config.slug,
            results=results,
            total_count=total
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Historie: {str(e)}")


@router.post("/scans/{scan_identifier}/trigger", response_model=TriggerResponse)
async def trigger_scan(scan_identifier: str, background_tasks: BackgroundTasks):
    """
    Startet einen Scan manuell
    
    Args:
        scan_identifier: Slug oder Name des Scans
        background_tasks: FastAPI BackgroundTasks für asynchrone Ausführung
    """
    try:
        job = jobs_store.get_job(scan_identifier)

        if not job:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden")

        # Volle Konfiguration inkl. entschlüsseltem NAS-Passwort (nur für den Scan-Lauf)
        scan_config = jobs_store.to_scan_config(job)

        # Prüfe ob bereits ein Scan läuft
        if scanner_service.is_scan_running(scan_config.slug):
            return TriggerResponse(
                scan_slug=scan_config.slug,
                message=f"Scan '{scan_config.name}' läuft bereits",
                triggered=False
            )
        
        # Starte Scan im Hintergrund
        background_tasks.add_task(scanner_service.run_scan, scan_config)
        
        return TriggerResponse(
            scan_slug=scan_config.slug,
            message=f"Scan '{scan_config.name}' wurde gestartet",
            triggered=True
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Starten des Scans: {str(e)}")


@router.post("/scans/{scan_identifier}/cancel", response_model=CancelResponse)
async def cancel_scan(scan_identifier: str):
    """
    Bricht einen laufenden Scan ab.

    Der Abbruch ist kooperativ: Scans laufen als Hintergrund-Task bzw. als
    Scheduler-Job, es gibt kein Task-Handle zum harten Beenden. Der Lauf prüft
    den Wunsch zwischen zwei Pfaden und bei jedem Poll der Größenabfrage, endet
    also in der Regel innerhalb weniger Sekunden. Der laufende DirSize-Task wird
    zusätzlich am NAS gestoppt, damit dort nicht weitergerechnet wird.

    Der Lauf wird mit Status 'cancelled' in der Historie gespeichert - bereits
    gemessene Pfade bleiben erhalten, gelten aber nicht als erfolgreicher Lauf.

    Args:
        scan_identifier: Slug oder Name des Scans
    """
    try:
        job = jobs_store.get_job(scan_identifier)

        if not job:
            raise HTTPException(
                status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden"
            )

        slug = job["slug"]
        if not scanner_service.request_cancel(slug):
            # Kein laufender Scan: bewusst HTTP 200 mit cancelling=false statt
            # eines Fehlers - dasselbe Muster wie beim Trigger, damit ein
            # doppelter Klick keine Fehlermeldung produziert.
            return CancelResponse(
                scan_slug=slug,
                message=f"Für '{job['name']}' läuft derzeit kein Scan",
                cancelling=False,
            )

        logger.info(f"Abbruch für Scan '{slug}' angefordert")
        return CancelResponse(
            scan_slug=slug,
            message=f"Abbruch für '{job['name']}' angefordert",
            cancelling=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Fehler beim Abbrechen des Scans: {str(e)}"
        )


# ========== STORAGE MANAGEMENT ENDPOINTS ==========

@router.get("/storage/stats")
async def get_storage_stats():
    """
    Gibt Statistiken über den Storage zurück
    
    Returns:
        Dictionary mit Statistiken (scan_count, nas_count, folder_count, db_size, etc.)
    """
    try:
        stats = storage.get_storage_stats()
        # Zusätzlich ausweisen, wie viel davon zu keinem Job mehr gehört -
        # sonst wächst dieser Anteil unbemerkt mit.
        try:
            orphans = _collect_orphans()
            stats["orphaned_scan_count"] = len(orphans)
            stats["orphaned_results"] = sum(entry["count"] for entry in orphans)
        except Exception as e:
            logger.warning(f"Verwaiste Ergebnisse nicht ermittelbar: {e}")
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen der Statistiken: {str(e)}")


@router.get("/storage/folders")
async def get_all_folders(
    nas_host: Optional[str] = None,
    scan_slug: Optional[str] = None
):
    """
    Gibt alle eindeutigen Ordner/Pfade zurück
    
    Args:
        nas_host: Optional: Filter nach NAS-Host
        scan_slug: Optional: Filter nach Scan-Slug
    
    Returns:
        Liste von Objekten mit nas_host und folder_path
    """
    try:
        folders = storage.get_all_folders(nas_host=nas_host, scan_slug=scan_slug)
        return {
            "folders": [
                {"nas_host": nas, "folder_path": folder}
                for nas, folder in folders
            ],
            "count": len(folders)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen der Ordner: {str(e)}")


@router.get("/storage/cleanup-preview")
async def get_cleanup_preview(
    days: int = 90,
    nas_host: Optional[str] = None,
    folder_path: Optional[str] = None,
    scan_slug: Optional[str] = None
):
    """
    Zeigt Vorschau der Bereinigung ohne zu löschen
    
    Args:
        days: Anzahl der Tage (Standard: 90)
        nas_host: Optional: Nur für dieses NAS
        folder_path: Optional: Nur für diesen Ordner
        scan_slug: Optional: Nur für diesen Scan (anhand slug)
    
    Returns:
        Dictionary mit Vorschau-Statistiken
    """
    try:
        return storage.cleanup_old_results(
            days=days,
            nas_host=nas_host,
            folder_path=folder_path,
            scan_slug=scan_slug,
            dry_run=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei Bereinigungs-Vorschau: {str(e)}")


@router.post("/storage/cleanup")
async def cleanup_storage(
    days: Optional[int] = None,
    nas_host: Optional[str] = None,
    folder_path: Optional[str] = None,
    scan_slug: Optional[str] = None
):
    """
    Bereinigt alte Scan-Ergebnisse
    
    Args:
        days: Anzahl der Tage (None = verwendet Standard aus Storage-Konfiguration)
        nas_host: Optional: Nur für dieses NAS
        folder_path: Optional: Nur für diesen Ordner
        scan_slug: Optional: Nur für diesen Scan (anhand slug)
    
    Returns:
        Dictionary mit Statistiken über die Bereinigung
    """
    try:
        stats = storage.cleanup_old_results(
            days=days,
            nas_host=nas_host,
            folder_path=folder_path,
            scan_slug=scan_slug,
            dry_run=False
        )
        return {
            "success": True,
            "message": f"{stats['deleted_count']} Einträge gelöscht",
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei Bereinigung: {str(e)}")


@router.delete("/storage/folders")
async def delete_folder_results(
    nas_host: Optional[str] = None,
    folder_path: Optional[str] = None,
    scan_slug: Optional[str] = None
):
    """
    Löscht Ergebnisse für spezifische Ordner/Pfade
    
    Args:
        nas_host: Optional: Nur für dieses NAS
        folder_path: Pfad des Ordners (erforderlich wenn nas_host oder scan_slug nicht gesetzt)
        scan_slug: Optional: Nur für diesen Scan (anhand slug)
    
    Returns:
        Dictionary mit Anzahl gelöschter Einträge
    """
    try:
        # Validierung: Mindestens ein Parameter muss gesetzt sein
        if not nas_host and not folder_path and not scan_slug:
            raise HTTPException(
                status_code=400,
                detail="Mindestens einer der Parameter (nas_host, folder_path, scan_slug) muss gesetzt sein"
            )
        
        deleted = storage.delete_folder_results(
            nas_host=nas_host,
            folder_path=folder_path,
            scan_slug=scan_slug
        )
        
        return {
            "success": True,
            "message": f"{deleted} Einträge gelöscht",
            "deleted_count": deleted
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")


def _collect_orphans() -> List[dict]:
    """
    Ergebnisse, zu denen es keinen Scan-Job mehr gibt.

    Sie entstehen, wenn ein Job ohne delete_history gelöscht wird - die
    Historie bleibt dann absichtlich erhalten, war über die API aber weder
    sicht- noch löschbar, weil jeder Endpunkt zuerst den Job nachschlägt.
    """
    known_slugs = {job["slug"] for job in jobs_store.list_jobs()}
    return [
        entry
        for entry in storage.get_slug_summary()
        if entry["scan_slug"] not in known_slugs
    ]


@router.get("/storage/orphans")
async def list_orphaned_results():
    """
    Listet Ergebnisse ohne zugehörigen Scan-Job.

    Returns:
        Übersicht je verwaistem Slug mit Anzahl und Zeitraum
    """
    try:
        orphans = _collect_orphans()
        return {
            "orphans": orphans,
            "scan_count": len(orphans),
            "total_results": sum(entry["count"] for entry in orphans),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Fehler beim Ermitteln verwaister Ergebnisse: {str(e)}"
        )


@router.delete("/storage/orphans")
async def delete_orphaned_results():
    """
    Löscht alle Ergebnisse, zu denen es keinen Scan-Job mehr gibt.

    Returns:
        Anzahl der gelöschten Läufe je Slug
    """
    try:
        orphans = _collect_orphans()
        deleted = []
        for entry in orphans:
            storage.clear_results(scan_slug=entry["scan_slug"])
            deleted.append(
                {"scan_slug": entry["scan_slug"], "deleted_count": entry["count"]}
            )
        return {
            "success": True,
            "message": f"{len(deleted)} verwaiste Scan-Historie(n) gelöscht",
            "deleted": deleted,
            "total_results": sum(item["deleted_count"] for item in deleted),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Fehler beim Löschen verwaister Ergebnisse: {str(e)}"
        )


@router.delete("/storage/scans/{scan_identifier}")
async def delete_scan_results(scan_identifier: str):
    """
    Löscht alle Ergebnisse eines Scans
    
    Args:
        scan_identifier: Slug oder Name des Scans
    
    Returns:
        Erfolgsmeldung
    """
    try:
        scan_config = get_scan_config_from_db(scan_identifier)

        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_identifier}' nicht gefunden")

        storage.clear_results(scan_slug=scan_config.slug)
        return {
            "success": True,
            "message": f"Alle Ergebnisse für Scan '{scan_config.name}' wurden gelöscht"
        }
    except HTTPException:
        # Sonst verschluckt der generische Zweig unten das 404 und macht daraus
        # einen 500er (der Client sieht "Fehler beim Löschen: 404: ...").
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")


@router.delete("/storage/all")
async def delete_all_results():
    """
    Löscht alle gespeicherten Ergebnisse
    
    ⚠️ WARNUNG: Diese Operation kann nicht rückgängig gemacht werden!
    
    Returns:
        Erfolgsmeldung
    """
    try:
        storage.clear_results()
        return {
            "success": True,
            "message": "Alle Ergebnisse wurden gelöscht"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")
