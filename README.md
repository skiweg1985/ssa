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
- Zugriff: nur `GET` auf `/api/prtg*` (Sensordaten, s.u.), `/api/scans*` (Status,
  Ergebnisse, Historie, Fortschritt), `/api/nas-metrics*` (Systemmetriken der NAS)
  und `/api/storage/stats` — kein Triggern, keine Verwaltung.
- Verwendung: Header `Authorization: Bearer <token>`.
- `/health` ist weiterhin ohne Token erreichbar (Up/Down-Checks).

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/scans
```

### PRTG: HTTP Data Advanced (empfohlen)

Vier Endpoints liefern fertige Sensordaten im PRTG-Format — PRTG legt die Kanäle
automatisch an, JSONPath-Filter entfallen:

| Endpoint | Sensor |
|---|---|
| `GET /api/prtg/scans/<slug>` | ein Sensor **pro Scan-Job** |
| `GET /api/prtg/server` | ein Sensor für den **Server selbst** |
| `GET /api/prtg/nas/<id-oder-name>/capacity` | Kapazität **pro NAS** (Volumes, Freigaben) |
| `GET /api/prtg/nas/<id-oder-name>/health` | Systemgesundheit **pro NAS** (SNMP) |

> **Achtung, verbreitete Fehlannahme:** Die CPU-, RAM- und Disk-Kanäle von
> `/api/prtg/server` messen den **Rechner, auf dem SSA läuft** — nicht das NAS.
> Für die Auslastung des NAS selbst ist der `health`-Sensor zuständig.

**Sensor anlegen:** Gerät → *Sensor hinzufügen* → **HTTP Data Advanced** → URL
eintragen → unter den erweiterten Einstellungen den Header
`Authorization: Bearer ssa_...` setzen. Scan-Intervall des Sensors sinnvollerweise
≥ Scan-Intervall des Jobs wählen.

**Kanäle pro Job:** Gesamtgröße · Ordner · Dateien · Scan-Dauer ·
Alter letzter Lauf · Alter letzte Daten · Status · Ordner OK · Ordner Fehler —
plus **ein Kanal je gescanntem Ordner** (Kanalname = Pfad, z.B. `/design`).

**Status-Kanal:**

| Wert | Bedeutung | Sensor |
|---|---|---|
| 0 | letzter Lauf erfolgreich | OK |
| 1 | Scan läuft gerade | OK |
| 2 | Job deaktiviert | OK |
| 3 | Job nicht eingeplant | Warning |
| 4 | letzter Lauf fehlgeschlagen | Error |

Messwerte stammen immer vom letzten **erfolgreichen** Lauf — ein Fehllauf macht
den Sensor rot, reißt die Charts aber nicht auf 0.

**Kanäle Server:** Uptime · CPU · RAM belegt/frei · Disk belegt/frei · Scheduler ·
Jobs gesamt/aktiv/laufend · Jobs mit Fehler · Jobs ohne Ergebnisse · Ältester Lauf ·
DB-Größe · Ergebnisse in DB · Konfigurationswarnungen.

### NAS-Systemmetriken

Zwei Sensoren je NAS, adressiert über **ID oder Verbindungsname**
(`/api/prtg/nas/NAS-01/capacity`). Getrennt, weil Kapazität und Hardware
unterschiedlich alarmiert werden und PRTG nur 50 Kanäle je Sensor zulässt.

**Kanäle `capacity`** (aus der File Station API, kein Zusatzaufwand am NAS):
Volumes · Volumes schreibgeschützt · Freigaben · Freigaben ohne Schreibrecht ·
Antwortzeit — plus **je Volume** Belegung %, frei und gesamt.

*Volumes schreibgeschützt* ist der wichtigste Einzelwert: Dieser Zustand tritt
bei vollem Speicher **und** bei abgestürztem RAID auf.

**Kanäle `health`** (via SNMP): Systemstatus · Temperatur · Netzteil ·
Systemlüfter · CPU-Lüfter · DSM-Update verfügbar · Platten · Platten nicht
normal · Höchste Plattentemperatur · RAID-Verbünde · RAID mit Fehler · RAID in
Wartung · CPU · RAM belegt — plus je RAID die Belegung, USV-Kanäle sofern ein
Gerät angeschlossen ist, und optional je Platte die Temperatur (`?disks=1`).

Statuskanäle nutzen durchgängig dieselbe Skala:

| Wert | Bedeutung | Sensor |
|---|---|---|
| 0 | Normal | OK |
| 1 | Wartung (z.B. RAID-Resync) | OK |
| 2 | Zustand unbekannt | Warning |
| 3 | Fehler | Error |

**SNMP einrichten** (nur für `health` nötig):

1. Am NAS: *Systemsteuerung → Terminal & SNMP → SNMP-Dienst aktivieren*.
2. In SSA: NAS-Verbindung bearbeiten → SNMP aktivieren, Version und Community
   bzw. v3-Zugangsdaten eintragen. Die Zugangsdaten werden verschlüsselt
   gespeichert (wie das DSM-Passwort) und nie über die API zurückgegeben.

SNMP ist der **einzige von Synology öffentlich dokumentierte** Weg zu
Temperatur, SMART, RAID-Status und USV — siehe
[DiskStation MIB Guide](https://global.download.synology.com/download/Document/MIBGuide/Synology_MIB_File.zip).
Die File Station API liefert diese Werte nicht.

### Generischer JSON-Endpoint

Für Grafana, eigene Dashboards und Skripte — ohne PRTG-Formatierung:

| Endpoint | Zweck |
|---|---|
| `GET /api/nas-metrics` | alle Systeme; `?connection_id=` filtert |
| `GET /api/nas-metrics/<id-oder-name>` | ein System |

`?groups=capacity,health` schränkt auf einzelne Quellen ein. Jede Quelle trägt
ihren eigenen `available`/`error`-Status: ein NAS ohne SNMP liefert weiterhin
vollständige Kapazitätsdaten.

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/nas-metrics/NAS-01
```

**Query-Parameter:**

| Parameter | Endpoint | Default | Wirkung |
|---|---|---|---|
| `folders` | `scans` | `1` | `0` = keine Ordner-Kanäle, nur Summen |
| `max_folders` | `scans` | `40` | Obergrenze für Ordner-Kanäle |
| `volumes` | `capacity` | `1` | `0` = keine Volume-Kanäle, nur Summen |
| `max_volumes` | `capacity` | `15` | Obergrenze für Volume-Kanäle |
| `disks` | `health` | `0` | `1` = zusätzlich ein Temperaturkanal je Platte |
| `max_disks` | `health` | `24` | Obergrenze für Platten-Kanäle |
| `limits` | alle | `1` | `0` = keine Schwellwerte (eigene in PRTG pflegen) |

**Gut zu wissen:**
- Metriken werden **live** geholt und ~60 s zwischengespeichert — `capacity`-
  und `health`-Sensor desselben NAS teilen sich also einen Abruf. Historie
  führt PRTG selbst; SSA speichert diese Werte nicht.
- Werte, die ein Modell nicht liefert (Temperatur, CPU, RAM), werden
  **weggelassen** statt als 0 gemeldet — die Sensormeldung nennt sie.
- PRTG identifiziert Kanäle über den **Namen** — wird ein Scan-Pfad umbenannt,
  entsteht ein neuer Kanal; der alte bleibt leer stehen und kann in PRTG gelöscht werden.
- PRTG unterstützt max. **50 Kanäle** pro Sensor; darüber wird gekappt (Hinweis
  erscheint in der Sensormeldung).
- Mitgelieferte Schwellwerte überschreiben in PRTG manuell gesetzte Limits —
  bei eigenen Schwellwerten `?limits=0` verwenden.
- Sensor erst **nach dem ersten erfolgreichen Scan** anlegen; vorher meldet der
  Endpoint bewusst einen Fehler statt Nullwerte.
- Fehler (unbekannter Job, noch keine Daten) kommen als HTTP **200** mit
  `prtg.error` — so wie PRTG es erwartet.

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/prtg/scans/design-scan
```

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
