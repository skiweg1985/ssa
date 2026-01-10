"""Config Models für YAML-Parsing"""
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class NASConfigYAML(BaseModel):
    """NAS-Zugangsdaten aus YAML"""
    host: str
    username: str
    password: str
    port: Optional[int] = None  # Optional: Port (Standard: 5001 für HTTPS, 5000 für HTTP)
    use_https: bool = True  # Ob HTTPS verwendet werden soll (Standard: True)
    verify_ssl: bool = True  # Ob SSL-Zertifikate verifiziert werden sollen (Standard: True)


class ScanTaskConfigYAML(BaseModel):
    """Scan-Task Konfiguration aus YAML"""
    name: str
    nas: NASConfigYAML
    # Listen für mehrere Werte
    shares: Optional[List[str]] = None
    folders: Optional[List[str]] = None
    paths: Optional[List[str]] = None
    interval: str
    enabled: bool = True

    @model_validator(mode='after')
    def validate_paths(self):
        """
        Validiert die Konfiguration.
        
        Mögliche Kombinationen:
        - shares (ohne folders) -> scannt alle shares
        - shares + folders -> scannt alle Kombinationen (share/folder1, share/folder2, ...)
          WICHTIG: Bei folders darf nur 1 Share angegeben werden!
        - paths -> scannt alle paths
        - shares + paths -> scannt alle shares UND alle paths
        - shares + folders + paths -> scannt share/folder Kombinationen UND alle paths
          WICHTIG: Bei folders darf nur 1 Share angegeben werden!
        """
        has_share = self.shares is not None
        has_path = self.paths is not None
        
        # Mindestens eines muss vorhanden sein
        if not has_share and not has_path:
            raise ValueError("Mindestens 'shares' ODER 'paths' muss angegeben werden")
        
        # Leere Listen sind nicht erlaubt
        if has_share and self.shares == []:
            raise ValueError("'shares' Liste darf nicht leer sein")
        
        if has_path and self.paths == []:
            raise ValueError("'paths' Liste darf nicht leer sein")
        
        # Folders nur mit shares
        if self.folders is not None:
            if not has_share:
                raise ValueError("'folders' kann nur zusammen mit 'shares' verwendet werden")
            
            if self.folders == []:
                raise ValueError("'folders' Liste darf nicht leer sein")
            
            # Wenn folders vorhanden ist, darf nur 1 Share angegeben werden
            if len(self.shares) > 1:
                raise ValueError("Wenn 'folders' angegeben ist, darf nur 1 Share in 'shares' angegeben werden")
        
        return self


class StorageConfigYAML(BaseModel):
    """Storage-Konfiguration aus YAML"""
    db_path: Optional[str] = None  # Optional: Vollständiger Pfad zur SQLite-Datenbank
    storage_dir: Optional[str] = None  # Optional: Verzeichnis für persistierte Daten (wird ignoriert wenn db_path gesetzt)


class ConfigYAML(BaseModel):
    """Haupt-Konfiguration aus YAML"""
    scans: list[ScanTaskConfigYAML]
    storage: Optional[StorageConfigYAML] = None  # Optional: Storage-Konfiguration