"""YAML Konfigurations-Loader"""
import yaml
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone
from app.models.config import ConfigYAML, ScanTaskConfigYAML

logger = logging.getLogger(__name__)

# Globale Variable für gesammelte Warnungen (für Health-Endpoint)
_config_warnings: List[Dict[str, str]] = []


def load_config(config_path: Optional[str] = None) -> ConfigYAML:
    """
    Lädt die YAML-Konfigurationsdatei mit Duplikat-Prüfung.
    Bei doppelten Slugs wird das neuere Scan (basierend auf Erstellungsdatum) verworfen.
    
    Args:
        config_path: Pfad zur config.yaml Datei. Wenn None, wird nach config.yaml im aktuellen Verzeichnis gesucht.
    
    Returns:
        ConfigYAML Objekt mit allen Scan-Tasks (ohne Duplikate)
    
    Raises:
        FileNotFoundError: Wenn die Config-Datei nicht gefunden wird
        yaml.YAMLError: Wenn die YAML-Datei ungültig ist
    """
    global _config_warnings
    _config_warnings = []  # Reset Warnungen
    
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
    
    # Prüfe auf Duplikate und entferne neuere
    config = _remove_duplicate_slugs(config)
    
    return config


def _remove_duplicate_slugs(config: ConfigYAML) -> ConfigYAML:
    """
    Entfernt Duplikate basierend auf Slug. Bei doppelten Slugs wird das neuere Scan verworfen.
    
    Args:
        config: ConfigYAML Objekt mit möglichen Duplikaten
    
    Returns:
        ConfigYAML Objekt ohne Duplikate
    """
    global _config_warnings
    
    # Gruppiere Scans nach Slug
    slug_groups: Dict[str, List[ScanTaskConfigYAML]] = {}
    for scan in config.scans:
        if scan.slug not in slug_groups:
            slug_groups[scan.slug] = []
        slug_groups[scan.slug].append(scan)
    
    # Finde Duplikate und behalte nur das älteste
    unique_scans: List[ScanTaskConfigYAML] = []
    for slug, scans in slug_groups.items():
        if len(scans) > 1:
            # Sortiere nach Erstellungsdatum (ältestes zuerst)
            scans_sorted = sorted(scans, key=lambda s: s.created_at or datetime.min.replace(tzinfo=timezone.utc))
            
            # Behalte das älteste
            kept_scan = scans_sorted[0]
            unique_scans.append(kept_scan)
            
            # Verwirf die neueren
            removed_scans = scans_sorted[1:]
            for removed_scan in removed_scans:
                warning_msg = (
                    f"WARNUNG: Duplikat-Slug '{slug}' gefunden. "
                    f"Scan '{removed_scan.name}' (erstellt: {removed_scan.created_at}) wurde verworfen, "
                    f"da Scan '{kept_scan.name}' (erstellt: {kept_scan.created_at}) älter ist."
                )
                logger.warning(warning_msg)
                _config_warnings.append({
                    "type": "duplicate_slug",
                    "slug": slug,
                    "removed_scan": removed_scan.name,
                    "removed_created_at": removed_scan.created_at.isoformat() if removed_scan.created_at else None,
                    "kept_scan": kept_scan.name,
                    "kept_created_at": kept_scan.created_at.isoformat() if kept_scan.created_at else None,
                    "message": warning_msg
                })
        else:
            unique_scans.append(scans[0])
    
    # Erstelle neue Config ohne Duplikate
    config.scans = unique_scans
    return config


def get_config_warnings() -> List[Dict[str, str]]:
    """
    Gibt die gesammelten Konfigurations-Warnungen zurück (für Health-Endpoint).
    
    Returns:
        Liste von Warnungen
    """
    return _config_warnings.copy()


def get_scan_config(config: ConfigYAML, scan_identifier: str) -> Optional[ScanTaskConfigYAML]:
    """
    Holt die Konfiguration für einen spezifischen Scan
    Unterstützt slug oder name als Identifier
    
    Args:
        config: ConfigYAML Objekt
        scan_identifier: Slug oder Name des Scans
    
    Returns:
        ScanTaskConfigYAML oder None wenn nicht gefunden
    """
    for scan in config.scans:
        if scan.slug == scan_identifier or scan.name == scan_identifier:
            return scan
    return None


def get_scan_config_by_slug(config: ConfigYAML, slug: str) -> Optional[ScanTaskConfigYAML]:
    """Holt die Konfiguration für einen Scan anhand seines Slugs"""
    for scan in config.scans:
        if scan.slug == slug:
            return scan
    return None


def get_scan_config_by_name(config: ConfigYAML, name: str) -> Optional[ScanTaskConfigYAML]:
    """Holt die Konfiguration für einen Scan anhand seines Namens"""
    for scan in config.scans:
        if scan.name == name:
            return scan
    return None
