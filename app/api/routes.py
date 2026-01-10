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
        Dict mit Status-Informationen (num_dir, num_file, total_size, waited, finished, current_path, progress_percent)
        oder 404 wenn Scan nicht läuft
        
        progress_percent: Prozentwert basierend auf dem letzten erfolgreichen Scan (0-100)
                         oder None wenn keine Historie vorhanden ist
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
        
        # Berechne Fortschritt basierend auf historischem Scan
        progress_percent = None
        last_completed = storage.get_latest_completed_result(scan_name)
        
        if last_completed and last_completed.results:
            # Hole path_status für pro-Ordner Berechnung
            path_status = progress.get("path_status", {})
            
            # Normalisiere Pfade für Vergleich (entferne führende/trailing Slashes)
            def normalize_path(p: str) -> str:
                """Normalisiert einen Pfad für Vergleich"""
                return p.strip().strip('/')
            
            # Erstelle Mapping von historischen Werten pro Pfad (normalisiert)
            historical_by_path = {}
            for item in last_completed.results:
                if item.success:
                    # Normalisiere Pfad für konsistenten Vergleich
                    normalized_path = normalize_path(item.folder_name)
                    historical_by_path[normalized_path] = {
                        "size": item.total_size.bytes if item.total_size else 0,
                        "dirs": item.num_dir or 0,
                        "files": item.num_file or 0,
                        "original_path": item.folder_name  # Behalte Original für Debugging
                    }
            
            # Erstelle normalisiertes Mapping von aktuellen Pfaden
            normalized_path_status = {}
            for path, status in path_status.items():
                normalized = normalize_path(path)
                # Wenn mehrere Pfade auf denselben normalisierten Pfad mappen, 
                # verwende den mit den höchsten Werten (aktuellster Status)
                if normalized not in normalized_path_status:
                    normalized_path_status[normalized] = status
                else:
                    # Behalte den Status mit höheren Werten
                    existing = normalized_path_status[normalized]
                    if status.get("total_size", 0) > existing.get("total_size", 0):
                        normalized_path_status[normalized] = status
            
            # Berechne Gesamtwerte des letzten erfolgreichen Scans (für Fallback)
            historical_total_size = sum(
                item.total_size.bytes 
                for item in last_completed.results 
                if item.success and item.total_size and item.total_size.bytes > 0
            )
            historical_total_dirs = sum(
                item.num_dir or 0 
                for item in last_completed.results 
                if item.success
            )
            historical_total_files = sum(
                item.num_file or 0 
                for item in last_completed.results 
                if item.success
            )
            
            # Berechne Fortschritt pro Ordner und gewichte nach Größe
            total_weighted_size_percent = 0.0
            total_weighted_dirs_percent = 0.0
            total_weighted_files_percent = 0.0
            total_weight = 0.0
            
            # Iteriere über alle historischen Pfade
            for normalized_path, historical in historical_by_path.items():
                # Hole aktuellen Status für diesen Pfad (falls vorhanden)
                current_path_status = normalized_path_status.get(normalized_path, {})
                current_size = current_path_status.get("total_size", 0) or 0
                current_dirs = current_path_status.get("num_dir", 0) or 0
                current_files = current_path_status.get("num_file", 0) or 0
                
                hist_size = historical["size"]
                hist_dirs = historical["dirs"]
                hist_files = historical["files"]
                
                # Gewicht basierend auf historischer Größe (wichtigste Metrik)
                # Verwende Größe als primäres Gewicht, da sie am genauesten ist
                if hist_size > 0:
                    weight = hist_size
                elif hist_dirs > 0:
                    weight = hist_dirs * 1000  # Fallback: verwende dirs als Gewicht
                elif hist_files > 0:
                    weight = hist_files  # Fallback: verwende files als Gewicht
                else:
                    weight = 1  # Minimales Gewicht für leere Ordner
                
                # Berechne Fortschritt für diesen Ordner
                # Wenn der Ordner noch nicht gestartet wurde, ist der Fortschritt 0%
                if hist_size > 0:
                    path_size_percent = min(100, max(0, (current_size / hist_size) * 100))
                else:
                    # Für leere Ordner: 100% wenn fertig, sonst 0%
                    path_size_percent = 100 if current_path_status.get("finished", False) else 0
                
                if hist_dirs > 0:
                    path_dirs_percent = min(100, max(0, (current_dirs / hist_dirs) * 100))
                else:
                    path_dirs_percent = 100 if current_path_status.get("finished", False) else 0
                
                if hist_files > 0:
                    path_files_percent = min(100, max(0, (current_files / hist_files) * 100))
                else:
                    path_files_percent = 100 if current_path_status.get("finished", False) else 0
                
                # Gewichtete Summe (jeder Ordner trägt entsprechend seiner Größe zum Gesamtfortschritt bei)
                total_weighted_size_percent += path_size_percent * weight
                total_weighted_dirs_percent += path_dirs_percent * weight
                total_weighted_files_percent += path_files_percent * weight
                total_weight += weight
            
            # Berechne gewichteten Durchschnitt
            if total_weight > 0:
                size_percent = total_weighted_size_percent / total_weight
                dirs_percent = total_weighted_dirs_percent / total_weight
                files_percent = total_weighted_files_percent / total_weight
            else:
                # Fallback: verwende aggregierte Werte wenn keine path_status verfügbar
                current_total_size = progress.get("total_size", 0) or 0
                current_total_dirs = progress.get("num_dir", 0) or 0
                current_total_files = progress.get("num_file", 0) or 0
                
                if historical_total_size > 0:
                    size_percent = min(100, max(0, (current_total_size / historical_total_size) * 100))
                else:
                    size_percent = 0
                
                if historical_total_dirs > 0:
                    dirs_percent = min(100, max(0, (current_total_dirs / historical_total_dirs) * 100))
                else:
                    dirs_percent = 0
                
                if historical_total_files > 0:
                    files_percent = min(100, max(0, (current_total_files / historical_total_files) * 100))
                else:
                    files_percent = 0
            
            # Gewichteter Durchschnitt der Metriken (Größe 70%, Ordner 20%, Dateien 10%)
            progress_percent = (size_percent * 0.7 + dirs_percent * 0.2 + files_percent * 0.1)
            progress_percent = round(progress_percent, 1)
        
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
            "scan_name": scan_name,
            "status": response_status,
            "progress": progress_with_percent
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
