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

Der interaktive CLI-Client ermöglicht Ad-hoc-Analysen von Verzeichnisgrößen.

Siehe [README_CLI.md](README_CLI.md) für Details zur Nutzung.

**Schnellstart:**

```bash
# Interaktiv starten
python explore_syno_api.py

# Eine Freigabe scannen
python explore_syno_api.py --share homes

# JSON-Ausgabe
python explore_syno_api.py --json --share homes
```

## FastAPI-Server

Der Server ermöglicht geplante Scans über eine REST API und Web-Interface.

Siehe [README_SERVER.md](README_SERVER.md) für Details zur Nutzung.

**Schnellstart:**

```bash
# Server starten
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Web-UI: http://localhost:8000
# Health: GET /health
```

## Sicherheit

- Standard ist **SSL-Verifizierung an**.
- Für self-signed Zertifikate: in `.env` `SYNO_VERIFY_SSL=false` oder in `config.yaml` `verify_ssl: false`.

## Tests

```bash
pytest
```

## Lizenz

Siehe `LICENSE`.
