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

Die Abhängigkeiten sind auf exakte Versionen gepinnt (`==`), damit jede
Installation dieselben Pakete bekommt. `requirements.txt` enthält
ausschließlich die **Laufzeit**-Abhängigkeiten – das Test-Werkzeug steht in
`requirements-dev.txt` und landet damit weder im Docker-Image noch im
Release-Paket (siehe [Tests](#tests)).

### Lokal auf macOS/Linux (venv)

Die App läuft ohne Anpassungen lokal, z.B. auf einem Mac – benötigt wird nur
Python 3.11+ und Netzwerkzugriff aufs NAS (alle Scans laufen über die
File Station API, nichts wird lokal gemountet):

```bash
git clone <repo-url> && cd ssa
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.yaml.example config.yaml   # anpassen

# Server starten (Web-UI: http://localhost:8080)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Alternativ das venv aktivieren (`source .venv/bin/activate`), dann funktionieren
`uvicorn`, `pytest` und `python` direkt ohne `.venv/bin/`-Präfix.

`install.sh`/`service.sh` (systemd) sind nur für den Dauerbetrieb unter Linux
gedacht und werden auf dem Mac nicht benötigt.

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
uvicorn app.main:app --host 0.0.0.0 --port 8080

# Web-UI: http://localhost:8080
# Health: GET /health
```

## Docker / Compose

Die App kann komplett als Container laufen — das Image baut das Frontend
selbst (Multi-Stage), es wird also weder Node noch Python auf dem Host benötigt:

```bash
# Passwort setzen (oder in .env neben der docker-compose.yml legen)
echo 'SSA_ADMIN_PASSWORD=dein-passwort' > .env

docker compose up -d
# Web-UI: http://localhost:8080 (Login: admin / dein Passwort)
```

- **Persistenz:** Das Volume `ssa-data` (→ `/app/data`) enthält die SQLite-DB
  (Historie, Jobs, verschlüsselte NAS-Creds) und den auto-generierten
  `secret.key`. Nicht löschen, sonst müssen NAS-Passwörter neu eingegeben werden.
- **Erst-Import:** Eine bestehende `config.yaml` kann optional read-only nach
  `/app/config.yaml` gemountet werden (auskommentierte Zeile in der
  `docker-compose.yml`) — sie wird beim ersten Start einmalig importiert.
- **Healthcheck** ist im Image integriert (`/health`).
- Ohne Compose: `docker build -t ssa . && docker run -d -p 8080:8080 -e SSA_ADMIN_PASSWORD=... -v ssa-data:/app/data ssa`

Der CI-Workflow baut das Image bei jedem PR und führt einen Boot-Smoke-Test
durch (Health, Login, Auth-Durchsetzung, Frontend-Auslieferung).

## Download & Start (fertiges Paket)

Wer die App ohne Node/Build laufen lassen will, lädt das fertige Paket vom
neuesten [GitHub Release](../../releases/latest) (`ssa-<version>.tar.gz` oder
`.zip`) – Backend inkl. bereits gebautem Frontend:

```bash
tar -xzf ssa-<version>.tar.gz && cd ssa-<version>
pip install -r requirements.txt
cp config.yaml.example config.yaml   # anpassen
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Die Release-Pakete werden per GitHub-Actions-Workflow
(`.github/workflows/release.yml`) automatisch erstellt, sobald ein Tag der
Form `v*` gepusht wird:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

Alternativ funktioniert weiterhin der klassische Weg: Repo klonen und direkt
starten – das gebaute Frontend (`frontend/dist/`) ist im Repo enthalten.

> **Für Maintainer:** Wie ein Release erstellt wird (Tag pushen, Workflow,
> Paketinhalt, Troubleshooting) steht in [RELEASING.md](RELEASING.md).

## Job-Verwaltung im Frontend

Scan-Jobs und NAS-Verbindungen werden **im Web-Frontend** verwaltet:

- **Scan-Jobs**: anlegen/bearbeiten/löschen über „Neuer Scan" bzw. das Aktionsmenü der Tabelle — inkl. Verzeichnisauswahl per NAS-Browser, Intervall-Presets oder Cron.
- **NAS-Verbindungen**: eigener Bereich (Topbar → Server-Icon) mit „Verbindung testen"; Passwörter werden **verschlüsselt** in der Datenbank gespeichert und nie wieder ans Frontend ausgeliefert.
- Bestehende `config.yaml`-Scans werden beim **ersten Start einmalig importiert**; danach ist die Datenbank die einzige Quelle.

## Monitoring (PRTG, Zabbix, Grafana …)

Für Monitoring-Systeme gibt es **statische, read-only API-Tokens**, die im
Frontend verwaltet werden (API-Modal → „API-Tokens verwalten" oder ⌘K):

- Token wird bei Erstellung **einmalig** angezeigt (gespeichert wird nur der Hash).
- Zugriff: nur `GET` auf `/api/monitor*` (Zustandsberichte, s.u.), `/api/prtg*`
  (PRTG-Sensordaten), `/api/scans*` (Status, Ergebnisse, Historie, Fortschritt)
  und `/api/storage/stats` — kein Triggern, keine Verwaltung.
- Verwendung: Header `Authorization: Bearer <token>`.
- `/health` ist weiterhin ohne Token erreichbar (Up/Down-Checks).

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/scans
```

### Endpoints für Monitoring-Systeme

| Endpoint | Wofür |
|---|---|
| `GET /api/monitor` | Gesamtzustand — ein Check für die ganze Instanz |
| `GET /api/monitor/scans` | alle Scan-Jobs, mit Roll-up und Problemliste |
| `GET /api/monitor/scans/<slug>` | ein einzelner Scan-Job |
| `GET /api/monitor/server` | Infrastruktur — Scheduler, System, Storage |
| `GET /api/prtg/scans/<slug>` | PRTG-Sensor pro Scan-Job |
| `GET /api/prtg/server` | PRTG-Sensor für den Server selbst |

Die `/api/monitor*`-Endpoints liefern den Zustand fertig ausgewertet: das Feld
`severity` (0 = OK, 1 = Warnung, 2 = kritisch) genügt für die Alarmentscheidung —
kein Zweit-Call, keine Client-Logik, kein Parsen von Cron-Ausdrücken. Für PRTG
gibt es stattdessen Sensordaten im Format „HTTP Data Advanced", die ihre Kanäle
selbst anlegen.

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/monitor
```

Siehe [README_MONITORING.md](README_MONITORING.md) für Details — Feldreferenz,
Beispielantworten, PRTG-Sensoreinrichtung und fertige Rezepte für Nagios,
Zabbix, Checkmk, Grafana und Uptime-Kuma.

## Sicherheit

- **Login erforderlich**: Das Frontend/die API ist per Passwort geschützt. Setze `SSA_ADMIN_PASSWORD` in der Umgebung (z.B. `.env`); Standard-Benutzer ist `admin` (änderbar via `SSA_ADMIN_USER`). Ohne gesetztes Passwort ist der Login deaktiviert.
- **Brute-Force-Schutz**: Nach mehreren Fehlversuchen wird der Login pro Client-IP gesperrt (HTTP 429 mit `Retry-After`). Jede weitere Sperre verdoppelt die Dauer, gedeckelt bei einer Stunde. Ein erfolgreicher Login setzt den Zähler zurück, damit legitime Nutzer nie ausgesperrt werden.

  | Variable | Default | Bedeutung |
  |---|---|---|
  | `SSA_LOGIN_MAX_ATTEMPTS` | `5` | Fehlversuche bis zur Sperre |
  | `SSA_LOGIN_WINDOW_SECONDS` | `300` | Zeitfenster, in dem Fehlversuche zusammenzählen |
  | `SSA_LOGIN_BLOCK_SECONDS` | `300` | Basis-Sperrdauer (verdoppelt sich progressiv) |
  | `SSA_TRUST_PROXY_HEADERS` | *(aus)* | `X-Forwarded-For` als Client-IP werten |

  ⚠️ `SSA_TRUST_PROXY_HEADERS` nur setzen, wenn die App **wirklich** hinter einem Reverse-Proxy steht, der den Header selbst schreibt. Ist die App direkt erreichbar, kann jeder Client das Limit mit einem gefälschten Header umgehen. Der Zähler liegt im Prozessspeicher – bei mehreren Workern/Instanzen zählt jeder Prozess für sich; dann gehört ein Limit zusätzlich in den vorgelagerten Proxy.
- **Verschlüsselte NAS-Passwörter**: gespeicherte Zugangsdaten werden mit einem Key aus `SSA_SECRET_KEY` bzw. der auto-generierten `data/secret.key` verschlüsselt. Bei Key-Verlust/-Rotation müssen die NAS-Passwörter neu eingegeben werden.
- Standard ist **SSL-Verifizierung an**.
- Für self-signed Zertifikate: SSL-Prüfung pro NAS-Verbindung im Frontend deaktivierbar (CLI: `SYNO_VERIFY_SSL=false`).

## Tests

Zum Testen zusätzlich die Entwicklungs-Abhängigkeiten installieren
(`requirements-dev.txt` zieht `requirements.txt` selbst mit):

```bash
pip install -r requirements-dev.txt
pytest
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).

## Sicherheit melden

Sicherheitslücken bitte **nicht** über öffentliche Issues melden, sondern über
den privaten Meldeweg — Details in [SECURITY.md](SECURITY.md).
