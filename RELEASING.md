# Release erstellen

Releases werden **automatisch von GitHub Actions** gebaut und veröffentlicht,
sobald ein Git-Tag der Form `v*` gepusht wird. Der zuständige Workflow ist
[`.github/workflows/release.yml`](.github/workflows/release.yml).

Es ist **kein** manueller Build nötig – der Workflow baut das Frontend frisch,
schnürt das Paket und hängt es ans Release.

---

## Schnellanleitung

```bash
# 1. Auf aktuellen main-Stand wechseln
git checkout main
git pull origin main

# 2. Tag mit v-Präfix setzen und pushen
git tag v1.0.0
git push origin v1.0.0
```

Das war's. Der Rest passiert automatisch:

1. GitHub Actions startet den **Release**-Workflow (Tab **Actions**).
2. Das Frontend wird gebaut (`npm ci && npm run build`).
3. Backend + gebautes Frontend + Konfig-Beispiele + Skripte werden gepackt.
4. Ein GitHub **Release** `v1.0.0` wird erstellt, mit zwei Download-Assets:
   - `ssa-v1.0.0.tar.gz`
   - `ssa-v1.0.0.zip`

Das fertige Release erscheint unter **Releases** (`/releases`).

---

## Wichtig: Das `v`-Präfix ist Pflicht

Der Workflow triggert nur auf Tags, die dem Muster `v*` entsprechen:

| Tag        | Löst Release aus? |
|------------|-------------------|
| `v1.0.0`   | ✅ ja             |
| `v2024.1`  | ✅ ja             |
| `1.0.0`    | ❌ **nein**       |
| `release-1`| ❌ nein           |

Ein Tag **ohne** `v` (z.B. `1.0.0`) wird ignoriert – es passiert dann nichts.

Die Version im Paketnamen kommt aus dem Tag: `v1.2.3` → `ssa-v1.2.3.tar.gz`.
Verwende [Semantic Versioning](https://semver.org/lang/de/) (`vMAJOR.MINOR.PATCH`).

---

## Testlauf ohne Release (optional)

Um Build + Packaging zu prüfen, ohne ein echtes Release anzulegen:

1. GitHub → Tab **Actions** → Workflow **Release** auswählen
2. **Run workflow** → Branch `main` → **Run workflow**

Der Lauf baut und packt alles und lädt die Pakete als **Workflow-Artefakt**
hoch (beim Run-Eintrag herunterladbar). Es wird **kein** Release erstellt und
kein Tag gesetzt – der Release-Schritt läuft nur bei echten Tag-Pushes
(`if: github.ref_type == 'tag'`). Die Version heißt dann `dev-<commit-sha>`.

---

## Paketinhalt

Jedes Release-Paket ist eigenständig lauffähig und enthält:

```
ssa-v1.0.0/
├── app/                  # FastAPI-Backend
├── explore_syno_api.py   # Synology-API-Client / CLI
├── frontend/dist/        # fertig gebautes Frontend (kein Node nötig)
├── requirements.txt
├── .env.example
├── README.md, README_CLI.md, README_SERVER.md
└── install.sh, service.sh, uninstall.sh
```

Nicht enthalten (bewusst): `frontend/src`, `node_modules`, Tests, Entwicklungs-Dateien.

### Installieren & Starten (Endnutzer)

```bash
tar -xzf ssa-v1.0.0.tar.gz && cd ssa-v1.0.0
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

---

## Troubleshooting

**Tag ohne `v` gepusht (z.B. `1.0.0`) – nichts passiert:**
Der Tag matcht `v*` nicht. Neu anlegen:
```bash
git tag -d 1.0.0            # lokal löschen
git push origin :1.0.0      # remote löschen
git tag v1.0.0
git push origin v1.0.0
```

**Release für einen Tag wiederholen / Tag verschieben:**
Ein bereits gepushter Tag löst nicht erneut aus. Tag löschen und neu setzen:
```bash
git tag -d v1.0.0
git push origin :v1.0.0     # ggf. bestehendes Release in der UI löschen
git tag v1.0.0
git push origin v1.0.0
```

**Fehler „release already exists":**
Tritt auf, wenn zum Tag bereits ein Release existiert (z.B. manuell in der UI
angelegt). Lösche das bestehende Release unter `/releases` und pushe den Tag neu,
damit der Workflow es sauber erstellt.

**Workflow läuft nicht an:**
Prüfe unter **Settings → Actions**, dass Actions aktiviert sind, und im Tab
**Actions**, ob der Lauf erschien. Der Workflow muss auf `main` vorhanden sein,
damit Tag-Pushes ihn auslösen.
