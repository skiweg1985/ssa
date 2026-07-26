# Synology Space Analyzer

Tooling, um **Verzeichnisgrößen auf einem Synology NAS** über die **File Station API** zu messen – entweder:
- **als CLI** für Ad-hoc Analysen
- **als FastAPI-Server** für geplante Scans + REST API

## Funktionen

- **Misst Größen** für Shares/Ordner/Pfade
- **Server** mit Scheduler (aus `config.yaml`) und Ergebnis-API
- **Persistente Historie** per SQLite (standardmäßig `data/history.db`)

## Installation

Drei Wege, je nachdem was Sie vorhaben:

| Weg | Wofür | Voraussetzung |
|---|---|---|
| **[Docker / Compose](#docker--compose)** – empfohlen | Betrieb | Docker |
| **[Release-Paket](#download--start-fertiges-paket)** | Betrieb ohne Docker, z.B. mit systemd | Python 3.11+ |
| **[Aus dem Quellcode](#aus-dem-quellcode-entwicklung)** | Entwicklung | Python 3.11+ und Node 22+ |

Für den Betrieb sind Docker und das Release-Paket die vorgesehenen Wege: Beide
bringen ein fertig gebautes Frontend mit, es wird also **kein Node** benötigt.
Das Git-Repository enthält bewusst nur Quellcode — `frontend/dist` wird dort
gebaut, wo es gebraucht wird (Docker-Stage 1 bzw. Release-Workflow).

### Aus dem Quellcode (Entwicklung)

Benötigt Python 3.11+ **und Node 22+** (letzteres für das Frontend) sowie
Netzwerkzugriff aufs NAS — alle Scans laufen über die File Station API, es wird
nichts lokal gemountet.

`dev.sh` nimmt die Einrichtung ab. Einmalig — legt `.venv` an, installiert
Python- und npm-Pakete und baut das Frontend:

```bash
git clone <repo-url> && cd ssa && ./dev.sh setup
```

Danach beide Server starten (Backend mit Reload, Vite mit Hot Reload):

```bash
./dev.sh
```

| Adresse | Zeigt |
|---|---|
| `http://localhost:5173` | Vite-Dev-Server — **hier entwickeln**, Hot Reload, `/api` wird aufs Backend geleitet |
| `http://localhost:8080` | Backend samt gebauter UI — der Stand, den auch Docker ausliefert |

Weitere Befehle:

| Befehl | Wofür |
|---|---|
| `./dev.sh backend` | nur das Backend |
| `./dev.sh frontend` | nur den Vite-Dev-Server |
| `./dev.sh build` | Frontend neu bauen (aktualisiert die UI unter `:8080`) |
| `./dev.sh test` | Testsuite; Argumente werden an pytest durchgereicht |

Die Ports lassen sich über `SSA_DEV_BACKEND_PORT` und `SSA_DEV_FRONTEND_PORT`
umstellen. Für den **Betrieb** ist `dev.sh` nicht gedacht — dafür `docker
compose` oder das Release-Paket.

<details>
<summary>Dieselben Schritte von Hand</summary>

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
npm --prefix frontend ci && npm --prefix frontend run build
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Alternativ das venv aktivieren (`source .venv/bin/activate`), dann funktionieren
`uvicorn`, `pytest` und `python` direkt ohne `.venv/bin/`-Präfix.

</details>

Eine `config.yaml` ist optional (`cp config.yaml.example config.yaml`) — sie
dient nur dem einmaligen Erst-Import; Scan-Jobs lassen sich vollständig im
Frontend anlegen. Für den Login muss `SSA_ADMIN_PASSWORD` gesetzt sein, z.B. in
einer `.env`.

Die Abhängigkeiten sind auf exakte Versionen gepinnt (`==`), damit jede
Installation dieselben Pakete bekommt. `requirements.txt` enthält
ausschließlich die **Laufzeit**-Abhängigkeiten – das Test-Werkzeug steht in
`requirements-dev.txt` und landet damit weder im Docker-Image noch im
Release-Paket (siehe [Tests](#tests)).

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

Das Paket enthält ein **fertig gebautes Frontend**, es wird also kein Node
benötigt. Wer stattdessen aus dem Git-Repository arbeitet, baut das Frontend
einmalig selbst — siehe [Aus dem Quellcode](#aus-dem-quellcode-entwicklung).

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
  (PRTG-Sensordaten), `/api/scans*` (Status, Ergebnisse, Historie, Fortschritt),
  `/api/nas-metrics*` (Systemmetriken der NAS)
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
| `GET /api/prtg/nas/<id>/capacity` | PRTG-Sensor: Volume-Belegung eines NAS |
| `GET /api/prtg/nas/<id>/health` | PRTG-Sensor: Temperatur, Platten, RAID (SNMP) |
| `GET /api/nas-metrics[/<id>]` | NAS-Systemmetriken als rohes JSON |

Die `/api/monitor*`-Endpoints liefern den Zustand fertig ausgewertet: das Feld
`severity` (0 = OK, 1 = Warnung, 2 = kritisch) genügt für die Alarmentscheidung —
kein Zweit-Call, keine Client-Logik, kein Parsen von Cron-Ausdrücken. Für PRTG
gibt es stattdessen Sensordaten im Format „HTTP Data Advanced", die ihre Kanäle
selbst anlegen.

Die `nas`-Endpoints messen die **NAS-Geräte selbst** — Kapazität, Temperatur,
Plattenstatus, RAID. Nicht zu verwechseln mit `/api/prtg/server`, dessen CPU-
und RAM-Kanäle den Rechner betreffen, auf dem SSA läuft.

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

Nach `./dev.sh setup` genügt:

```bash
./dev.sh test
```

Argumente werden an pytest durchgereicht, z.B. `./dev.sh test test_prtg_api.py -v`.

Von Hand — `requirements-dev.txt` zieht `requirements.txt` selbst mit:

```bash
pip install -r requirements-dev.txt
pytest
```

`frontend/dist` wird für die Tests nicht benötigt: Fehlt ein Build, legt
`conftest.py` einen Platzhalter an, damit die Tests der SPA-Auslieferung
(Path-Traversal-Schutz) auch im frischen Klon laufen. Ein vorhandener Build
wird nie überschrieben.

## Lizenz

MIT — siehe [LICENSE](LICENSE).

## Sicherheit melden

Sicherheitslücken bitte **nicht** über öffentliche Issues melden, sondern über
den privaten Meldeweg — Details in [SECURITY.md](SECURITY.md).
