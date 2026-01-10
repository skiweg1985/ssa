# Synology Space Analyzer

Tooling, um **Verzeichnisgrößen auf einem Synology NAS** über die **File Station API** zu messen – entweder:
- **als CLI** für Ad-hoc Analysen
- **als FastAPI-Server** für geplante Scans + REST API

## Funktionen

- **Misst Größen** für Shares/Ordner/Pfade
- **Server** mit Scheduler (aus `config.yaml`) und Ergebnis-API
- **Persistente Historie** per SQLite (standardmäßig `data/history.db`)

## Installation

```bash
pip install -r requirements.txt
```

## CLI

### Konfiguration (`.env`)

```bash
cp .env.example .env
```

```env
SYNO_HOST=192.168.1.100
SYNO_USERNAME=admin
SYNO_PASSWORD=your_password_here
```

Bei self-signed Zertifikaten:

```env
SYNO_VERIFY_SSL=false
```

### Beispiele

```bash
# Interaktiv starten (Shares auswählen)
python explore_syno_api.py

# Eine Freigabe scannen
python explore_syno_api.py --share homes

# Direkte Pfade scannen (mehrere möglich)
python explore_syno_api.py --path homes/user1/Documents backup/daily

# Nur Shares auflisten
python explore_syno_api.py --list-shares

# JSON-Ausgabe (z.B. für Skripte)
python explore_syno_api.py --json --share homes
```

## FastAPI-Server

### Konfiguration (`config.yaml`)

Kopieren und anpassen:

```bash
cp config.yaml.example config.yaml
```

Beispiel (eine Aufgabe):

```yaml
scans:
  - name: "homes_scan"
    enabled: true
    interval: "6h"        # oder Cron, z.B. "0 */6 * * *"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      use_https: true
      verify_ssl: true
    shares: ["homes"]     # alternativ: paths: ["homes/user1/Documents"]
    folders: null         # nur sinnvoll mit genau 1 Share
    paths: null
```

### Start

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- **Web-UI**: `http://localhost:8000`
- **Health**: `GET /health`

### API

- `GET /api/scans` – alle Scan-Jobs + Status
- `GET /api/scans/{scan_name}/results` – letztes Ergebnis
- `POST /api/scans/{scan_name}/trigger` – Scan manuell starten
- `POST /api/config/reload` – `config.yaml` neu laden

## Sicherheit

- Standard ist **SSL-Verifizierung an**.
- Für self-signed Zertifikate: in `.env` `SYNO_VERIFY_SSL=false` oder in `config.yaml` `verify_ssl: false`.

## Tests

```bash
pytest
```

## Lizenz

Siehe `LICENSE`.
