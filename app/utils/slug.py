"""Utility-Funktionen für die Slug-Generierung"""
import re
import unicodedata


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
