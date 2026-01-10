"""API Routes für FastAPI"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from datetime import datetime

from app.models.scan import (
    ScanResult,
    ScanStatus,
    ScanListResponse,
    TriggerResponse,
    ScanHistoryResponse,
    NASConfigPublic
)
from app.services.storage import storage
from app.services.scanner import scanner_service
from app.services.scheduler import scheduler_service
from app.config.loader import load_config, get_scan_config

router = APIRouter()


@router.get("/scans", response_model=ScanListResponse)
async def get_scans():
    """
    Gibt eine Liste aller konfigurierten Scans mit Status zurück
    """
    try:
        config = load_config()
        scan_statuses = []
        
        for scan_config in config.scans:
            # Prüfe zuerst, ob Scan gerade läuft
            is_running = scanner_service.is_scan_running(scan_config.name)
            
            # Hole letztes Ergebnis
            latest_result = storage.get_latest_result(scan_config.name)
            
            # Hole Job-Info vom Scheduler
            job_info = scheduler_service.get_job_info(scan_config.name)
            
            status = "pending"
            last_run = None
            next_run = None
            
            # Wenn Scan läuft, setze Status auf "running"
            if is_running:
                status = "running"
            elif latest_result:
                status = latest_result.status
                last_run = latest_result.timestamp
            
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
                scan_name=scan_config.name,
                status=status,
                last_run=last_run,
                next_run=next_run,
                enabled=scan_config.enabled,
                shares=scan_config.shares,
                folders=scan_config.folders,
                paths=scan_config.paths,
                nas=nas_config_public,
                interval=scan_config.interval
            )
            scan_statuses.append(scan_status)
        
        return ScanListResponse(scans=scan_statuses)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Scans: {str(e)}")


@router.get("/scans/{scan_name}", response_model=ScanStatus)
async def get_scan(scan_name: str):
    """
    Gibt Details eines spezifischen Scans zurück
    """
    try:
        config = load_config()
        scan_config = get_scan_config(config, scan_name)
        
        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_name}' nicht gefunden")
        
        # Prüfe zuerst, ob Scan gerade läuft
        is_running = scanner_service.is_scan_running(scan_name)
        
        # Hole letztes Ergebnis
        latest_result = storage.get_latest_result(scan_name)
        
        # Hole Job-Info vom Scheduler
        job_info = scheduler_service.get_job_info(scan_name)
        
        status = "pending"
        last_run = None
        next_run = None
        
        # Wenn Scan läuft, setze Status auf "running"
        if is_running:
            status = "running"
        elif latest_result:
            status = latest_result.status
            last_run = latest_result.timestamp
        
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
            scan_name=scan_name,
            status=status,
            last_run=last_run,
            next_run=next_run,
            enabled=scan_config.enabled,
            shares=scan_config.shares,
            folders=scan_config.folders,
            paths=scan_config.paths,
            nas=nas_config_public,
            interval=scan_config.interval
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden des Scans: {str(e)}")


@router.get("/scans/{scan_name}/status", response_model=ScanStatus)
async def get_scan_status(scan_name: str):
    """
    Gibt den Status eines Scans zurück
    """
    return await get_scan(scan_name)


@router.get("/scans/{scan_name}/progress")
async def get_scan_progress(scan_name: str):
    """
    Gibt die aktuellen intermediären Status-Informationen eines laufenden Scans zurück.
    
    Args:
        scan_name: Name des Scans
    
    Returns:
        Dict mit Status-Informationen (num_dir, num_file, total_size, waited, finished, current_path)
        oder 404 wenn Scan nicht läuft
    """
    try:
        config = load_config()
        scan_config = get_scan_config(config, scan_name)
        
        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_name}' nicht gefunden")
        
        # Prüfe ob Scan läuft
        if not scanner_service.is_scan_running(scan_name):
            raise HTTPException(
                status_code=404,
                detail=f"Scan '{scan_name}' läuft aktuell nicht"
            )
        
        # Hole Status-Informationen
        progress = scanner_service.get_scan_progress(scan_name)
        
        if not progress:
            raise HTTPException(
                status_code=404,
                detail=f"Keine Status-Informationen für Scan '{scan_name}' verfügbar"
            )
        
        return {
            "scan_name": scan_name,
            "status": "running",
            "progress": progress
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen des Status: {str(e)}")


@router.get("/scans/{scan_name}/results", response_model=ScanResult)
async def get_scan_results(scan_name: str, latest: bool = True):
    """
    Gibt die Ergebnisse eines Scans zurück
    
    Args:
        scan_name: Name des Scans
        latest: Wenn True, nur das neueste Ergebnis. Wenn False, alle Ergebnisse.
    """
    try:
        config = load_config()
        scan_config = get_scan_config(config, scan_name)
        
        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_name}' nicht gefunden")
        
        if latest:
            result = storage.get_latest_result(scan_name)
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"Keine Ergebnisse für Scan '{scan_name}' gefunden"
                )
            return result
        else:
            results = storage.get_all_results(scan_name)
            if not results:
                raise HTTPException(
                    status_code=404,
                    detail=f"Keine Ergebnisse für Scan '{scan_name}' gefunden"
                )
            # Gibt das neueste zurück (letztes in der Liste)
            return results[-1]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Ergebnisse: {str(e)}")


@router.get("/scans/{scan_name}/history", response_model=ScanHistoryResponse)
async def get_scan_history(scan_name: str):
    """
    Gibt die komplette Historie aller Ergebnisse eines Scans zurück
    
    Args:
        scan_name: Name des Scans
    """
    try:
        config = load_config()
        scan_config = get_scan_config(config, scan_name)
        
        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_name}' nicht gefunden")
        
        results = storage.get_all_results(scan_name)
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Keine Ergebnisse für Scan '{scan_name}' gefunden"
            )
        
        return ScanHistoryResponse(
            scan_name=scan_name,
            results=results,
            total_count=len(results)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Historie: {str(e)}")


@router.post("/scans/{scan_name}/trigger", response_model=TriggerResponse)
async def trigger_scan(scan_name: str, background_tasks: BackgroundTasks):
    """
    Startet einen Scan manuell
    
    Args:
        scan_name: Name des Scans
        background_tasks: FastAPI BackgroundTasks für asynchrone Ausführung
    """
    try:
        config = load_config()
        scan_config = get_scan_config(config, scan_name)
        
        if not scan_config:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_name}' nicht gefunden")
        
        # Prüfe ob bereits ein Scan läuft
        if scanner_service.is_scan_running(scan_name):
            return TriggerResponse(
                scan_name=scan_name,
                message=f"Scan '{scan_name}' läuft bereits",
                triggered=False
            )
        
        # Starte Scan im Hintergrund
        background_tasks.add_task(scanner_service.run_scan, scan_config)
        
        return TriggerResponse(
            scan_name=scan_name,
            message=f"Scan '{scan_name}' wurde gestartet",
            triggered=True
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Starten des Scans: {str(e)}")


@router.post("/config/reload")
async def reload_config():
    """
    Lädt die Konfiguration manuell neu und aktualisiert alle Jobs
    """
    try:
        result = scheduler_service.reload_config()
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"],
                "added_scans": result.get("added_scans", []),
                "updated_scans": result.get("updated_scans", []),
                "removed_scans": result.get("removed_scans", []),
                "total_scans": result.get("total_scans", 0)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Fehler beim Neuladen der Konfiguration")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Neuladen der Konfiguration: {str(e)}"
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
        return storage.get_storage_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen der Statistiken: {str(e)}")


@router.get("/storage/folders")
async def get_all_folders(
    nas_host: Optional[str] = None,
    scan_name: Optional[str] = None
):
    """
    Gibt alle eindeutigen Ordner/Pfade zurück
    
    Args:
        nas_host: Optional: Filter nach NAS-Host
        scan_name: Optional: Filter nach Scan-Name
    
    Returns:
        Liste von Objekten mit nas_host und folder_path
    """
    try:
        folders = storage.get_all_folders(nas_host=nas_host, scan_name=scan_name)
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
    scan_name: Optional[str] = None
):
    """
    Zeigt Vorschau der Bereinigung ohne zu löschen
    
    Args:
        days: Anzahl der Tage (Standard: 90)
        nas_host: Optional: Nur für dieses NAS
        folder_path: Optional: Nur für diesen Ordner
        scan_name: Optional: Nur für diesen Scan
    
    Returns:
        Dictionary mit Vorschau-Statistiken
    """
    try:
        return storage.cleanup_old_results(
            days=days,
            nas_host=nas_host,
            folder_path=folder_path,
            scan_name=scan_name,
            dry_run=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei Bereinigungs-Vorschau: {str(e)}")


@router.post("/storage/cleanup")
async def cleanup_storage(
    days: Optional[int] = None,
    nas_host: Optional[str] = None,
    folder_path: Optional[str] = None,
    scan_name: Optional[str] = None
):
    """
    Bereinigt alte Scan-Ergebnisse
    
    Args:
        days: Anzahl der Tage (None = verwendet Standard aus Storage-Konfiguration)
        nas_host: Optional: Nur für dieses NAS
        folder_path: Optional: Nur für diesen Ordner
        scan_name: Optional: Nur für diesen Scan
    
    Returns:
        Dictionary mit Statistiken über die Bereinigung
    """
    try:
        stats = storage.cleanup_old_results(
            days=days,
            nas_host=nas_host,
            folder_path=folder_path,
            scan_name=scan_name,
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
    scan_name: Optional[str] = None
):
    """
    Löscht Ergebnisse für spezifische Ordner/Pfade
    
    Args:
        nas_host: Optional: Nur für dieses NAS
        folder_path: Pfad des Ordners (erforderlich wenn nas_host oder scan_name nicht gesetzt)
        scan_name: Optional: Nur für diesen Scan
    
    Returns:
        Dictionary mit Anzahl gelöschter Einträge
    """
    try:
        # Validierung: Mindestens ein Parameter muss gesetzt sein
        if not nas_host and not folder_path and not scan_name:
            raise HTTPException(
                status_code=400,
                detail="Mindestens einer der Parameter (nas_host, folder_path, scan_name) muss gesetzt sein"
            )
        
        deleted = storage.delete_folder_results(
            nas_host=nas_host,
            folder_path=folder_path,
            scan_name=scan_name
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


@router.delete("/storage/scans/{scan_name}")
async def delete_scan_results(scan_name: str):
    """
    Löscht alle Ergebnisse eines Scans
    
    Args:
        scan_name: Name des Scans
    
    Returns:
        Erfolgsmeldung
    """
    try:
        storage.clear_results(scan_name=scan_name)
        return {
            "success": True,
            "message": f"Alle Ergebnisse für Scan '{scan_name}' wurden gelöscht"
        }
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
