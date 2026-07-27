# CLI-Client

Der interaktive CLI-Client (`explore_syno_api.py`) ermöglicht Ad-hoc-Analysen von Verzeichnisgrößen auf einem Synology NAS über die File Station API.

## Funktionen

- Interaktive Auswahl von Freigaben und Ordnern
- Parallele und sequenzielle Ausführungsmodi
- Unterstützung für Shares, Ordner und vollständige Pfade
- JSON-Ausgabe für Skripte und Automatisierung
- Volume-Informationen
- Automatisches Scannen aller Freigaben

## Konfiguration

### Umgebungsvariablen (`.env`)

Erstelle eine `.env`-Datei im Projektverzeichnis:

```env
SYNO_HOST=192.168.1.100
SYNO_USERNAME=admin
SYNO_PASSWORD=your_password_here
SYNO_VERIFY_SSL=true
SYNO_DEFAULT_EXECUTION_MODE=parallel
SYNO_MAX_PARALLEL_TASKS=3
```

**Parameter:**

- `SYNO_HOST`: Hostname oder IP-Adresse des NAS
- `SYNO_USERNAME`: Benutzername für API-Zugriff
- `SYNO_PASSWORD`: Passwort
- `SYNO_VERIFY_SSL`: SSL-Zertifikat-Verifizierung (`true`/`false`, Standard: `true`)
- `SYNO_DEFAULT_EXECUTION_MODE`: Standard-Ausführungsmodus (`parallel` oder `sequential`)
- `SYNO_MAX_PARALLEL_TASKS`: Maximale Anzahl paralleler Tasks (1-10, Standard: 3)

Bei selbst-signierten Zertifikaten:

```env
SYNO_VERIFY_SSL=false
```

Alternativ kann `SYNO_INSECURE=true` verwendet werden.

## Verwendung

### Interaktiver Modus

Starte den Client ohne Parameter für interaktive Auswahl:

```bash
python explore_syno_api.py
```

Der Client zeigt eine interaktive Auswahl:
1. Liste aller verfügbaren Freigaben
2. Auswahl einer oder mehrerer Freigaben
3. Auswahl von Ordnern innerhalb der Freigaben
4. Anzeige der Ergebnisse in einer formatierten Tabelle

### Kommandozeilen-Optionen

#### Freigaben scannen

```bash
# Eine Freigabe scannen
python explore_syno_api.py --share homes

# Alle Freigaben scannen (nur mit JSON-Ausgabe)
python explore_syno_api.py --json --all
```

#### Ordner scannen

```bash
# Einzelnen Ordner innerhalb einer Freigabe
python explore_syno_api.py --share backup --folder daily

# Mehrere Ordner (komma-separiert)
python explore_syno_api.py --share backup --folder "daily,weekly,monthly"
```

#### Vollständige Pfade scannen

```bash
# Einzelner Pfad
python explore_syno_api.py --path homes/user1/Documents

# Mehrere Pfade (Leerzeichen-getrennt)
python explore_syno_api.py --path homes/user1/Documents backup/daily

# Mehrere Pfade (komma-separiert)
python explore_syno_api.py --path "homes/user1/Documents,backup/daily"
```

#### Unterordner einschließen

```bash
# Scanne Freigabe inklusive aller Unterordner
python explore_syno_api.py --share homes --include-subfolders
```

#### Weitere Optionen

```bash
# Nur verfügbare Freigaben auflisten
python explore_syno_api.py --list-shares

# JSON-Ausgabe (für Skripte)
python explore_syno_api.py --json --share homes

# Volume-Informationen anzeigen
python explore_syno_api.py --volumes --share homes

# Ausführungsmodus festlegen
python explore_syno_api.py --mode sequential --share homes
python explore_syno_api.py --mode parallel --share homes

# SSL-Verifizierung deaktivieren (CLI-Flag)
python explore_syno_api.py --insecure --share homes
```

## Ausführungsmodi

### Parallel (Standard)

Scans werden parallel ausgeführt, was bei mehreren Pfaden schneller ist. Die Anzahl paralleler Tasks wird durch `SYNO_MAX_PARALLEL_TASKS` begrenzt (Standard: 3, Maximum: 10).

### Sequenziell

Scans werden nacheinander ausgeführt. Nützlich bei Ressourcenbeschränkungen oder wenn parallele API-Aufrufe Probleme verursachen.

## Ausgabeformate

### Interaktive Ausgabe

Standardmäßig zeigt der Client eine formatierte Tabelle mit:
- Pfad
- Größe (in Bytes und menschenlesbaren Einheiten)
- Anzahl Dateien
- Anzahl Ordner
- Zeitstempel

### JSON-Ausgabe

Mit `--json` wird die Ausgabe als JSON formatiert:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "results": [
    {
      "path": "/homes/user1/Documents",
      "size_bytes": 1073741824,
      "size_unit": "GB",
      "size": 1.0,
      "file_count": 150,
      "folder_count": 25
    }
  ],
  "total": {
    "size_bytes": 1073741824,
    "size_unit": "GB",
    "size": 1.0
  }
}
```

Die JSON-Ausgabe eignet sich für:
- Weiterverarbeitung in Skripten
- Integration in Monitoring-Systeme
- Automatisierung

## Validierungen

Der Client prüft folgende Kombinationen:

- `--path` kann nicht zusammen mit `--share` oder `--folder` verwendet werden
- `--folder` erfordert `--share`
- `--all` funktioniert nur mit `--json`

## Fehlerbehandlung

Bei Verbindungsfehlern oder API-Fehlern zeigt der Client detaillierte Fehlermeldungen. Häufige Probleme:

- **SSL-Zertifikat-Fehler**: Verwende `--insecure` oder setze `SYNO_VERIFY_SSL=false`
- **Authentifizierungsfehler**: Prüfe Benutzername und Passwort in `.env`
- **Freigabe nicht gefunden**: Verwende `--list-shares` um verfügbare Freigaben anzuzeigen

## Performance

Die Performance hängt ab von:
- Anzahl zu scannender Pfade
- Größe der Verzeichnisse
- Netzwerk-Latenz zum NAS
- Ausgewählter Ausführungsmodus

Für große Scans empfiehlt sich der parallele Modus mit angepasster `SYNO_MAX_PARALLEL_TASKS`-Einstellung.
