"""YAML Konfigurations-Loader"""
import yaml
import os
from pathlib import Path
from typing import Optional, List
from app.models.config import ConfigYAML, ScanTaskConfigYAML


def load_config(config_path: Optional[str] = None) -> ConfigYAML:
    """
    Lädt die YAML-Konfigurationsdatei
    
    Args:
        config_path: Pfad zur config.yaml Datei. Wenn None, wird nach config.yaml im aktuellen Verzeichnis gesucht.
    
    Returns:
        ConfigYAML Objekt mit allen Scan-Tasks
    
    Raises:
        FileNotFoundError: Wenn die Config-Datei nicht gefunden wird
        yaml.YAMLError: Wenn die YAML-Datei ungültig ist
    """
    if config_path is None:
        # Suche nach config.yaml im aktuellen Verzeichnis oder im Projekt-Root
        current_dir = Path(__file__).parent.parent.parent
        possible_paths = [
            current_dir / "config.yaml",
            Path.cwd() / "config.yaml",
            Path.home() / ".syno-analyzer" / "config.yaml"
        ]
        
        for path in possible_paths:
            if path.exists():
                config_path = str(path)
                break
        
        if config_path is None:
            raise FileNotFoundError(
                f"Konfigurationsdatei nicht gefunden. Gesucht in: {[str(p) for p in possible_paths]}"
            )
    
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {config_path}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    if config_data is None:
        raise ValueError("Konfigurationsdatei ist leer")
    
    # Validiere die Konfiguration mit Pydantic
    config = ConfigYAML(**config_data)
    
    return config


def get_scan_config(config: ConfigYAML, scan_name: str) -> Optional[ScanTaskConfigYAML]:
    """
    Holt die Konfiguration für einen spezifischen Scan
    
    Args:
        config: ConfigYAML Objekt
        scan_name: Name des Scans
    
    Returns:
        ScanTaskConfigYAML oder None wenn nicht gefunden
    """
    for scan in config.scans:
        if scan.name == scan_name:
            return scan
    return None
