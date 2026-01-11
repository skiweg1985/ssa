"""Utility-Funktionen für Slug- und UID-Generierung"""
import re
import unicodedata
import hashlib
from typing import List, Set


def generate_slug(name: str) -> str:
    """
    Generiert einen URL-freundlichen Slug aus einem Namen.
    
    Args:
        name: Der Name, aus dem der Slug generiert werden soll
    
    Returns:
        Ein URL-freundlicher Slug (nur Kleinbuchstaben, Zahlen, Bindestriche)
    """
    # Normalisiere Unicode (z.B. ä -> a, ö -> o)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    
    # Konvertiere zu Kleinbuchstaben
    name = name.lower()
    
    # Ersetze Leerzeichen und Unterstriche durch Bindestriche
    name = re.sub(r'[\s_]+', '-', name)
    
    # Entferne alle Zeichen, die nicht alphanumerisch oder Bindestriche sind
    name = re.sub(r'[^a-z0-9\-]', '', name)
    
    # Entferne mehrfache Bindestriche
    name = re.sub(r'-+', '-', name)
    
    # Entferne führende und trailing Bindestriche
    name = name.strip('-')
    
    # Falls leer, generiere einen Fallback
    if not name:
        name = 'scan'
    
    return name


def generate_short_uid(name: str) -> str:
    """
    Generiert eine kurze, eindeutige UID (8 Zeichen) deterministisch basierend auf dem Namen.
    
    Die UID ist deterministisch - derselbe Name produziert immer dieselbe UID.
    Dies stellt sicher, dass UIDs stabil bleiben, auch wenn die Konfiguration neu geladen wird.
    
    Args:
        name: Der Name, der als Basis für die UID verwendet wird
    
    Returns:
        Eine kurze UID (8 Zeichen, alphanumerisch)
    """
    # Normalisiere den Namen für konsistente UID-Generierung
    # (ähnlich wie beim Slug, aber ohne Bindestriche zu entfernen)
    normalized = unicodedata.normalize('NFKD', name)
    normalized = normalized.encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower().strip()
    
    # Erstelle Hash nur aus dem normalisierten Namen (deterministisch)
    hash_obj = hashlib.sha256(normalized.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Nimm die ersten 8 Zeichen
    return hash_hex[:8]


def ensure_unique_slugs(slugs: List[str]) -> List[str]:
    """
    Stellt sicher, dass alle Slugs eindeutig sind.
    Fügt bei Duplikaten einen Suffix hinzu (z.B. -2, -3).
    
    Args:
        slugs: Liste von Slugs, die eindeutig gemacht werden sollen
    
    Returns:
        Liste von eindeutigen Slugs
    """
    seen: Set[str] = set()
    result: List[str] = []
    
    for slug in slugs:
        original_slug = slug
        counter = 1
        
        while slug in seen:
            counter += 1
            slug = f"{original_slug}-{counter}"
        
        seen.add(slug)
        result.append(slug)
    
    return result
