"""Pydantic Models für Scan-Ergebnisse und Konfiguration"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NASConfig(BaseModel):
    """NAS-Zugangsdaten"""
    host: str = Field(..., description="NAS Hostname oder IP-Adresse")
    username: str = Field(..., description="Benutzername")
    password: str = Field(..., description="Passwort")
    verify_ssl: bool = Field(default=True, description="SSL-Zertifikat verifizieren")


class ScanTaskConfig(BaseModel):
    """Konfiguration für einen Scan-Task"""
    name: str = Field(..., description="Eindeutiger Name des Scan-Tasks")
    nas: NASConfig = Field(..., description="NAS-Zugangsdaten")
    share: Optional[str] = Field(None, description="Freigabe-Name")
    folder: Optional[str] = Field(None, description="Ordner innerhalb der Freigabe")
    path: Optional[str] = Field(None, description="Vollständiger Pfad (alternativ zu share/folder)")
    interval: str = Field(..., description="Cron-Format Intervall (z.B. '0 */6 * * *')")
    enabled: bool = Field(default=True, description="Ob der Scan aktiviert ist")


class ScanConfig(BaseModel):
    """Haupt-Konfigurationsmodell"""
    scans: List[ScanTaskConfig] = Field(..., description="Liste der Scan-Tasks")


class TotalSize(BaseModel):
    """Größen-Informationen"""
    bytes: int = Field(..., description="Größe in Bytes")
    formatted: float = Field(..., description="Formatierte Größe")
    unit: str = Field(..., description="Einheit (B, KB, MB, GB, TB, PB)")


class ScanResultItem(BaseModel):
    """Einzelnes Scan-Ergebnis für einen Ordner"""
    folder_name: str = Field(..., description="Name des gescannten Ordners")
    success: bool = Field(..., description="Ob der Scan erfolgreich war")
    num_dir: Optional[int] = Field(None, description="Anzahl der Verzeichnisse")
    num_file: Optional[int] = Field(None, description="Anzahl der Dateien")
    total_size: Optional[TotalSize] = Field(None, description="Gesamtgröße")
    elapsed_time_ms: Optional[int] = Field(None, description="Verstrichene Zeit in Millisekunden")
    error: Optional[str] = Field(None, description="Fehlermeldung bei Fehlschlag")


class ScanResult(BaseModel):
    """Vollständiges Scan-Ergebnis mit Timestamp"""
    scan_name: str = Field(..., description="Name des Scan-Tasks")
    timestamp: datetime = Field(..., description="Zeitstempel des Scans (ISO 8601)")
    status: str = Field(..., description="Status: 'running', 'completed', 'failed'")
    results: List[ScanResultItem] = Field(default_factory=list, description="Liste der Scan-Ergebnisse")
    error: Optional[str] = Field(None, description="Fehlermeldung bei Fehlschlag")


class NASConfigPublic(BaseModel):
    """Öffentliche NAS-Konfiguration (ohne Passwort)"""
    host: str = Field(..., description="NAS Hostname oder IP-Adresse")
    username: str = Field(..., description="Benutzername")
    port: Optional[int] = Field(None, description="Port (Standard: 5001 für HTTPS, 5000 für HTTP)")
    use_https: bool = Field(True, description="Ob HTTPS verwendet wird")
    verify_ssl: bool = Field(True, description="Ob SSL-Zertifikate verifiziert werden")


class ScanStatus(BaseModel):
    """Status eines Scan-Tasks"""
    scan_name: str = Field(..., description="Name des Scan-Tasks")
    status: str = Field(..., description="Status: 'running', 'completed', 'failed', 'pending'")
    last_run: Optional[datetime] = Field(None, description="Zeitpunkt des letzten Laufs")
    next_run: Optional[datetime] = Field(None, description="Zeitpunkt des nächsten geplanten Laufs")
    enabled: bool = Field(..., description="Ob der Scan aktiviert ist")
    shares: Optional[List[str]] = Field(None, description="Konfigurierte Shares")
    folders: Optional[List[str]] = Field(None, description="Konfigurierte Folders")
    paths: Optional[List[str]] = Field(None, description="Konfigurierte Paths")
    nas: Optional[NASConfigPublic] = Field(None, description="NAS-Konfiguration (ohne Passwort)")
    interval: Optional[str] = Field(None, description="Cron-Format Intervall")


class ScanListResponse(BaseModel):
    """Response für Liste aller Scans"""
    scans: List[ScanStatus] = Field(..., description="Liste aller Scan-Status")


class TriggerResponse(BaseModel):
    """Response für manuellen Scan-Trigger"""
    scan_name: str = Field(..., description="Name des Scan-Tasks")
    message: str = Field(..., description="Status-Meldung")
    triggered: bool = Field(..., description="Ob der Scan erfolgreich gestartet wurde")


class ScanHistoryResponse(BaseModel):
    """Response für Scan-Historie"""
    scan_name: str = Field(..., description="Name des Scan-Tasks")
    results: List[ScanResult] = Field(..., description="Liste aller Scan-Ergebnisse")
    total_count: int = Field(..., description="Gesamtanzahl der Ergebnisse")
