# FastAPI-Server

Der FastAPI-Server ermöglicht geplante Scans über eine REST API und ein Web-Interface. Scans werden automatisch basierend auf einer YAML-Konfiguration ausgeführt und Ergebnisse in einer SQLite-Datenbank gespeichert.

## Funktionen

- Automatisches Scheduling von Scans (Cron oder Interval-Format)
- REST API für Scan-Management und Ergebnisse
- Web-Interface für Status und Ergebnisse
- Persistente Speicherung in SQLite
- Automatische Bereinigung alter Ergebnisse
- Health-Check mit Systemressourcen
- Konfiguration ohne Neustart neu laden

## Konfiguration

### `config.yaml`

Kopiere `config.yaml.example` zu `config.yaml` und passe die Werte an:

```yaml
scans:
  - name: "homes_scan"
    enabled: true
    interval: "6h"        # oder Cron: "0 */6 * * *"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      port: null          # null = automatisch (5001 für HTTPS, 5000 für HTTP)
      use_https: true
      verify_ssl: true
    shares: ["homes"]      # oder paths: ["homes/user1/Documents"]
    folders: null         # nur mit genau 1 Share
    paths: null
```

### Scan-Konfiguration

**Grundlegende Parameter:**

- `name`: Eindeutiger Name des Scans (für Anzeige)
- `slug`: Optional - URL-freundlicher Slug (wird automatisch aus `name` generiert wenn nicht angegeben)
- `enabled`: Aktiviert/deaktiviert den Scan (`true`/`false`)
- `interval`: Zeitplan (siehe unten)
- `nas`: NAS-Verbindungsparameter
- `shares`: Liste von Freigaben
- `folders`: Liste von Ordnern (nur mit genau 1 Share)
- `paths`: Liste vollständiger Pfade

**Hinweis zu Slugs:**
- Slugs werden automatisch aus dem Namen generiert (URL-freundlich, nur Kleinbuchstaben, Zahlen, Bindestriche)
- Slugs werden in API-URLs verwendet (z.B. `/api/scans/{scan_slug}/results`)
- Bei doppelten Slugs wird das neuere Scan verworfen (basierend auf Erstellungsdatum)

**Interval-Formate:**

- **Einfaches Format**: `"6h"`, `"30m"`, `"1d"` (Stunden/Minuten/Tage)
- **Cron-Format**: `"0 */6 * * *"` (Minute Stunde Tag Monat Wochentag)

Beispiele:
- `"6h"` - Alle 6 Stunden
- `"0 2 * * *"` - Täglich um 2 Uhr
- `"*/30 * * * *"` - Alle 30 Minuten
- `"0 0 * * 0"` - Wöchentlich am Sonntag um Mitternacht

**Pfad-Konfiguration:**

Es können verschiedene Kombinationen verwendet werden:

1. **Nur Shares**: `shares: ["homes", "backup"]`
2. **Shares + Ordner**: `shares: ["backup"]`, `folders: ["daily", "weekly"]` (nur 1 Share erlaubt)
3. **Vollständige Pfade**: `paths: ["homes/user1/Documents", "backup/daily"]`
4. **Kombinationen**: Shares + Pfade, oder Shares + Folders + Pfade

## Start

### Entwicklung

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Produktion

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Als Systemd-Service

Verwende `install.sh` für Installation als Systemd-Service:

```bash
sudo ./install.sh
```

Das Install-Script:
- Fragt nach dem Server-Port (Standard: 8080, kann auch als Umgebungsvariable `PORT` gesetzt werden)
- Prüft, ob `config.yaml` existiert und bietet an, `config.yaml.example` zu kopieren
- Erstellt den Systemd-Service mit konfiguriertem Port

Der Service startet automatisch beim Booten.

## Web-Interface

Nach dem Start ist das Web-Interface verfügbar unter:

```
http://localhost:8080
```

Der Port kann beim Start mit `--port` angepasst werden oder beim Install-Script konfiguriert werden.

Das Interface zeigt:
- Status aller konfigurierten Scans
- Fortschrittsanzeige für laufende Scans (mit Prozentangabe und Progress-Bar)
- Letzte Ergebnisse
- Nächste geplante Ausführung
- Möglichkeit, Scans manuell zu starten

## REST API

### Scan-Management

#### Alle Scans abrufen

```http
GET /api/scans
```

Gibt Liste aller konfigurierten Scans mit Status zurück.

**Response:**
```json
{
  "scans": [
    {
      "scan_slug": "homes-scan",
      "scan_name": "homes_scan",
      "status": "completed",
      "last_run": "2024-01-15T10:30:00Z",
      "next_run": "2024-01-15T16:30:00Z",
      "enabled": true,
      "shares": ["homes"],
      "interval": "6h"
    }
  ]
}
```

#### Einzelnen Scan abrufen

```http
GET /api/scans/{scan_slug}
```

Gibt Details eines spezifischen Scans zurück. Unterstützt auch den Scan-Namen als Fallback.

**Parameter:**
- `scan_slug`: URL-freundlicher Slug des Scans (z.B. `homes-scan`) oder Scan-Name

#### Scan-Status abrufen

```http
GET /api/scans/{scan_slug}/status
```

#### Scan-Fortschritt abrufen

```http
GET /api/scans/{scan_slug}/progress
```

Gibt den aktuellen Fortschritt eines laufenden Scans zurück.

**Response:**
```json
{
  "scan_slug": "homes-scan",
  "scan_name": "homes_scan",
  "status": "running",
  "progress": {
    "num_dir": 25664,
    "num_file": 1344600,
    "total_size": 9936676294163,
    "waited": 0,
    "finished": false,
    "current_path": "/homes/user1/Documents",
    "progress_percent": 45.3,
    "path_status": {
      "/homes/user1/Documents": {
        "num_dir": 12832,
        "num_file": 672300,
        "total_size": 4968338147081,
        "waited": 0,
        "finished": false
      }
    }
  }
}
```

**Felder:**
- `num_dir`, `num_file`, `total_size`: Aggregierte Werte aller gescannten Ordner
- `waited`: Maximale Wartezeit (längster laufender Scan)
- `finished`: `true` nur wenn alle erwarteten Ordner fertig sind
- `current_path`: Aktuell gescannter Pfad
- `progress_percent`: Fortschritt in Prozent (0-100), basierend auf historischen Werten
- `path_status`: Status pro Ordner (für Scans mit mehreren Pfaden)

**Fortschrittsberechnung:**
- Bei Scans mit mehreren Ordnern wird der Fortschritt pro Ordner berechnet und gewichtet aggregiert
- Die Gewichtung basiert auf der historischen Größe jedes Ordners
- Größere Ordner haben mehr Einfluss auf den Gesamtfortschritt
- Der Fortschritt wird nur angezeigt, wenn historische Daten verfügbar sind

#### Scan-Ergebnisse abrufen

```http
GET /api/scans/{scan_slug}/results?latest=true
```

**Parameter:**
- `scan_slug`: URL-freundlicher Slug des Scans (z.B. `homes-scan`) oder Scan-Name
- `latest`: `true` für neuestes Ergebnis (Standard), `false` für alle

**Response:**
```json
{
  "scan_slug": "homes-scan",
  "scan_name": "homes_scan",
  "timestamp": "2024-01-15T10:30:00Z",
  "status": "completed",
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

#### Scan-Historie abrufen

```http
GET /api/scans/{scan_slug}/history
```

Gibt alle gespeicherten Ergebnisse eines Scans zurück.

**Parameter:**
- `scan_slug`: URL-freundlicher Slug des Scans (z.B. `homes-scan`) oder Scan-Name

#### Scan manuell starten

```http
POST /api/scans/{scan_slug}/trigger
```

Startet einen Scan sofort, unabhängig vom Zeitplan.

**Parameter:**
- `scan_slug`: URL-freundlicher Slug des Scans (z.B. `homes-scan`) oder Scan-Name

**Response:**
```json
{
  "scan_slug": "homes-scan",
  "message": "Scan 'homes_scan' wurde gestartet",
  "triggered": true
}
```

### Konfiguration

#### Konfiguration neu laden

```http
POST /api/config/reload
```

Lädt `config.yaml` neu und aktualisiert alle geplanten Jobs ohne Server-Neustart.

**Response:**
```json
{
  "success": true,
  "message": "Konfiguration erfolgreich neu geladen",
  "added_scans": ["new_scan"],
  "updated_scans": ["homes_scan"],
  "removed_scans": [],
  "total_scans": 2
}
```

### Storage-Management

#### Storage-Statistiken

```http
GET /api/storage/stats
```

Gibt Statistiken über gespeicherte Ergebnisse zurück:
- Anzahl Scans
- Anzahl NAS-Systeme
- Anzahl Ordner
- Datenbankgröße
- Ältester/Neuester Eintrag
- Auto-Cleanup-Einstellungen

#### Alle Ordner abrufen

```http
GET /api/storage/folders?nas_host=192.168.1.100&scan_slug=homes-scan
```

**Parameter:**
- `nas_host`: Filter nach NAS-Host
- `scan_slug`: Filter nach Scan-Slug (URL-freundlich, z.B. `homes-scan`)

#### Bereinigung-Vorschau

```http
GET /api/storage/cleanup-preview?days=90&nas_host=192.168.1.100
```

Zeigt Vorschau der zu löschenden Einträge ohne zu löschen.

**Parameter:**
- `days`: Anzahl Tage (Standard: 90)
- `nas_host`: Filter nach NAS-Host
- `folder_path`: Filter nach Ordner-Pfad
- `scan_slug`: Filter nach Scan-Slug (URL-freundlich, z.B. `homes-scan`)

#### Bereinigung durchführen

```http
POST /api/storage/cleanup?days=90
```

Löscht alte Ergebnisse älter als die angegebene Anzahl Tage.

#### Ordner-Ergebnisse löschen

```http
DELETE /api/storage/folders?nas_host=192.168.1.100&folder_path=/homes/user1
```

Löscht Ergebnisse für spezifische Ordner/Pfade.

#### Scan-Ergebnisse löschen

```http
DELETE /api/storage/scans/{scan_slug}
```

Löscht alle Ergebnisse eines Scans.

**Parameter:**
- `scan_slug`: URL-freundlicher Slug des Scans (z.B. `homes-scan`) oder Scan-Name

#### Alle Ergebnisse löschen

```http
DELETE /api/storage/all
```

Löscht alle gespeicherten Ergebnisse.

### Health-Check

```http
GET /health
```

Gibt erweiterte Health-Informationen zurück:
- Server-Status und Uptime
- Systemressourcen (CPU, RAM, Disk) - wenn `psutil` installiert
- Scheduler-Status
- Storage-Statistiken
- Laufende Scans

## Datenbank

Ergebnisse werden in einer SQLite-Datenbank gespeichert:

- **Standard-Pfad**: `data/history.db`
- **Automatische Bereinigung**: Konfigurierbar über Storage-Service
- **Backup**: Regelmäßige Backups empfohlen

## Scheduler

Der Scheduler verwendet APScheduler für die Ausführung geplanter Scans:

- Startet automatisch beim Server-Start
- Lädt Konfiguration aus `config.yaml`
- Unterstützt Cron- und Interval-Formate
- Deaktivierte Scans werden nicht ausgeführt
- Fehlerbehandlung mit Logging

## Logging

Logs werden standardmäßig auf `INFO`-Level ausgegeben:

- Scan-Starts und -Abschlüsse
- Fehler und Warnungen
- Scheduler-Ereignisse
- API-Anfragen

Für detailliertere Logs kann das Log-Level angepasst werden.

## Sicherheit

- SSL-Verifizierung standardmäßig aktiviert
- Passwörter werden nicht in API-Responses zurückgegeben
- CORS konfigurierbar (Standard: alle Origins erlaubt - für Produktion einschränken)
- `config.yaml` sollte nicht in Git committed werden

## Fortschrittsanzeige

Bei laufenden Scans wird der Fortschritt in Echtzeit angezeigt:

- **Pro-Ordner-Berechnung**: Bei Scans mit mehreren Ordnern wird der Fortschritt für jeden Ordner separat berechnet
- **Gewichtete Aggregation**: Der Gesamtfortschritt wird gewichtet nach der historischen Größe jedes Ordners berechnet
- **Korrekte finished-Prüfung**: Ein Scan wird erst als fertig markiert, wenn alle erwarteten Ordner gescannt wurden
- **Pfadnormalisierung**: Pfade werden konsistent normalisiert, um korrekte Zuordnung zwischen historischen und aktuellen Werten zu gewährleisten

Die Fortschrittsanzeige ist im Web-Interface sichtbar und kann auch über die REST API abgerufen werden.

## Performance

- Scans laufen asynchron im Hintergrund
- Parallele Ausführung mehrerer Scans möglich
- SQLite-Datenbank für schnelle Abfragen
- Automatische Bereinigung verhindert Datenbankwachstum
- Fortschritts-Updates werden effizient aggregiert

## Fehlerbehandlung

- Fehlgeschlagene Scans werden mit Status `failed` markiert
- Fehlermeldungen werden in Scan-Ergebnissen gespeichert
- Server läuft weiter, auch wenn einzelne Scans fehlschlagen
- Scheduler versucht Scans erneut zum nächsten geplanten Zeitpunkt
