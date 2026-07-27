# Release erstellen

Releases werden **automatisch von GitHub Actions** gebaut und veröffentlicht,
sobald ein Git-Tag der Form `v*` gepusht wird. Der zuständige Workflow ist
[`../.github/workflows/release.yml`](../.github/workflows/release.yml).

Es ist **kein** manueller Build nötig – der Workflow baut das Frontend frisch,
schnürt das Paket und hängt es ans Release.

---

## Schnellanleitung

```bash
# 1. Auf aktuellen main-Stand wechseln
git checkout main
git pull origin main

# 2. Version im Code auf die neue Nummer ziehen (ohne v-Präfix)
#    - app/main.py:  version="..." der FastAPI-App
#    - frontend/:    npm version 2.0.0 --no-git-tag-version
#    Danach committen und nach main mergen – der Tag soll den Bump enthalten.

# 3. Tag mit v-Präfix setzen und pushen
git tag v2.0.0
git push origin v2.0.0
```

Das war's. Der Rest passiert automatisch:

1. GitHub Actions startet den **Release**-Workflow (Tab **Actions**).
2. Das **Container-Image** wird für `linux/amd64` und `linux/arm64` gebaut,
   nach GHCR gepusht und signiert (siehe [Container-Image](#container-image)).
3. Das Frontend wird gebaut (`npm ci && npm run build`).
4. Backend + gebautes Frontend + Konfig-Beispiele + Skripte werden gepackt.
5. Die Release-Notes werden erzeugt (siehe unten).
6. Ein GitHub **Release** `v2.0.0` wird erstellt, mit zwei Download-Assets:
   - `ssa-v2.0.0.tar.gz`
   - `ssa-v2.0.0.zip`

Das fertige Release erscheint unter **Releases** (`/releases`).

Schritt 2 läuft **vor** dem Rest (`needs: docker-image`): die Release-Notes
enthalten eine `docker pull`-Anleitung, und die darf nicht auf ein Image zeigen,
das noch gar nicht in der Registry liegt. Kehrseite: schlägt der Image-Build
fehl, entsteht auch kein Release mit den Archiven.

---

## Release-Notes

Die Notes bestehen aus zwei Teilen, die getrennt entstehen:

**Der Kopf** – „Das Wichtigste", Breaking Changes, Upgrade-Hinweise – wird von
einem Sprachmodell aus den Commits seit dem letzten Tag geschrieben. Zuständig
ist [`scripts/release_notes.py`](../scripts/release_notes.py), das über OpenRouter
läuft.

**Die Liste der Pull Requests** kommt von GitHub selbst und ist damit
vollständig und korrekt. Gegliedert wird sie nach den Labels der PRs; die
Kategorien stehen in [`../.github/release.yml`](../.github/release.yml).

### Einrichtung (einmalig)

| Was | Wo | Wert |
|---|---|---|
| `OPENROUTER_API_KEY` | Settings → Secrets and variables → Actions → **Secrets** | Key von [openrouter.ai/keys](https://openrouter.ai/keys) |
| `RELEASE_NOTES_MODEL` | Settings → Secrets and variables → Actions → **Variables** | Modell-Slug von [openrouter.ai/models](https://openrouter.ai/models), z.B. `anthropic/claude-opus-4.1` |

Für das Container-Image ist **kein Secret** nötig – GHCR akzeptiert das
`GITHUB_TOKEN` des Workflows. Einmalig ist dort aber die Paket-Sichtbarkeit
umzustellen, siehe [Container-Image](#container-image).

Das Modell ist bewusst eine Variable ohne Default: ein fest eingebauter Slug
veraltet und lässt das Release mit einem 404 auflaufen. Zum Wechseln reicht es,
die Variable zu ändern – kein Commit nötig.

**Fällt der Schritt aus** – Secret fehlt, Modell antwortet nicht –, läuft das
Release trotzdem durch und enthält dann nur die PR-Liste. Im Actions-Log steht
in dem Fall eine Warnung.

### Notes vorab ansehen

Der Kopf lässt sich lokal erzeugen, bevor der Tag gesetzt wird:

```bash
export OPENROUTER_API_KEY=sk-or-...
export RELEASE_NOTES_MODEL=anthropic/claude-opus-4.1
python3 scripts/release_notes.py v1.0.0 HEAD
```

### PRs labeln

Damit die Gliederung greift, brauchen die PRs Labels. Nachträglich labeln
funktioniert auch – die Notes werden erst beim Release ausgewertet, nicht beim
Merge. Verwendet werden `breaking-change`, `enhancement`, `bug`,
`race-condition`, `robustness`, `security`, `documentation`, `chore`,
`dependencies` und `ci`. Ein PR ohne passendes Label landet unter „Sonstiges".

---

## Wichtig: `vMAJOR.MINOR.PATCH` ist Pflicht

Der Workflow triggert auf Tags nach dem Muster `v*`. Für die **Image-Tags**
reicht das aber nicht – die brauchen gültiges
[Semantic Versioning](https://semver.org/lang/de/):

| Tag         | Löst Release aus? | Image-Tags         |
|-------------|-------------------|--------------------|
| `v1.2.3`    | ✅ ja             | `1.2.3`, `1.2`, `latest` |
| `v1.2.3-rc.1` | ✅ ja           | `1.2.3-rc.1` (kein `latest`) |
| `v2024.1`   | ✅ ja             | ⚠️ **keine** – kein gültiges SemVer |
| `1.0.0`     | ❌ **nein**       | –                  |
| `release-1` | ❌ nein           | –                  |

Ein Tag **ohne** `v` (z.B. `1.0.0`) wird ignoriert – es passiert dann nichts.

`v2024.1` würde zwar ein Release erzeugen, aber der Image-Push liefe ins Leere:
`docker/metadata-action` schreibt dann nur eine Warnung ins Log und vergibt gar
keinen Tag. **Also immer dreiteilig taggen.**

Die Version im Paketnamen kommt aus dem Tag: `v1.2.3` → `ssa-v1.2.3.tar.gz`.
Bei den Image-Tags fällt das `v` weg – Registry-Tags werden üblicherweise ohne
Präfix geschrieben.

---

## Testlauf ohne Release (optional)

Um Build + Packaging zu prüfen, ohne ein echtes Release anzulegen:

1. GitHub → Tab **Actions** → Workflow **Release** auswählen
2. **Run workflow** → Branch `main` → **Run workflow**

Der Lauf baut und packt alles und lädt die Pakete als **Workflow-Artefakt**
hoch (beim Run-Eintrag herunterladbar). Es wird **kein** Release erstellt und
kein Tag gesetzt – der Release-Schritt läuft nur bei echten Tag-Pushes
(`if: github.ref_type == 'tag'`). Die Version heißt dann `dev-<commit-sha>`.

Das Container-Image wird dabei **gebaut, aber nicht gepusht** – auch nicht der
GHCR-Login läuft. Der Lauf ist damit eine vollwertige Prüfung des
Multi-Arch-Builds (inklusive arm64) ohne jede Nebenwirkung, dauert dadurch aber
spürbar länger als früher.

Die erste Verteidigungslinie ist allerdings die CI: der Job **Docker (arm64
baubar)** in [`ci.yml`](.github/workflows/ci.yml) baut das Image bei jedem PR
für arm64. Ein fehlendes aarch64-Wheel nach einem Dependency-Update fällt damit
schon dort auf – und nicht erst beim Release, wo es auch die Archive blockiert.

---

## Paketinhalt

Jedes Release-Paket ist eigenständig lauffähig und enthält:

```
ssa-v1.0.0/
├── app/                  # FastAPI-Backend
├── explore_syno_api.py   # Synology-API-Client / CLI
├── frontend/dist/        # fertig gebautes Frontend (kein Node nötig)
├── docs/                 # CLI-, Server-, Monitoring- und Betriebsdoku
├── requirements.txt
├── .env.example
├── README.md
└── install.sh, service.sh, uninstall.sh
```

Nicht enthalten (bewusst): `frontend/src`, `node_modules`, Tests,
`docs/design.md`, das Synology-API-Referenz-PDF und weitere
Entwicklungs-Dateien.

### Installieren & Starten (Endnutzer)

```bash
tar -xzf ssa-v1.0.0.tar.gz && cd ssa-v1.0.0
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

---

## Container-Image

Jedes Release veröffentlicht zusätzlich ein Image in der **GitHub Container
Registry**:

```
ghcr.io/skiweg1985/ssa
```

Architekturen: `linux/amd64` und `linux/arm64` (ein Manifest, Docker wählt
selbst). Der arm64-Teil wird auf dem amd64-Runner unter QEMU gebaut – das ist
der langsamste Schritt im Release, typisch 5–12 Minuten.

**Welche Tags entstehen:**

| Git-Tag       | Image-Tags                   | `latest`? |
|---------------|------------------------------|-----------|
| `v2.1.0`      | `2.1.0`, `2.1`               | ✅ ja     |
| `v2.1.0-rc.1` | `2.1.0-rc.1`                 | ❌ nein   |
| `v2024.1`     | keine (kein SemVer)          | ❌ nein   |

Ein Prerelease bekommt bewusst weder `latest` noch den verkürzten Tag – ein
Release-Candidate darf nicht der Standard-Pull sein. Ein nacktes `2` gibt es
ebenfalls nicht: das wäre das Versprechen „jede 2.x ist kompatibel", und bei
einer App mit Datenvolume ist das zu stark.

Jedes Image bekommt eine signierte **Build-Provenance**, die den Digest an
Commit und Workflow-Lauf bindet:

```bash
gh attestation verify oci://ghcr.io/skiweg1985/ssa:2.1.0 --repo skiweg1985/ssa
```

### Einrichtung (einmalig, vor dem ersten echten Release)

Der erste Push legt das Paket automatisch an – **aber privat**. Bis das
umgestellt ist, schlägt jedes `docker pull` aus den Release-Notes fehl. Das ist
der einzige Handgriff, der sich nicht automatisieren lässt; ein
`workflow_dispatch` löst es nicht, weil der per Design nicht pusht.

1. Wegwerf-Tag pushen, um das Paket anzulegen (setzt **kein** `latest`, legt
   also nichts fest):
   ```bash
   git tag v2.0.1-rc.1 && git push origin v2.0.1-rc.1
   ```
2. `github.com/users/skiweg1985/packages/container/ssa/settings` → **Danger
   Zone** → *Change visibility* → **Public**.
3. Auf derselben Seite prüfen: unter *Manage Actions access* muss
   `skiweg1985/ssa` mit Rolle *Write* stehen (passiert automatisch über das
   OCI-Label `org.opencontainers.image.source`).
4. Von außen gegenprüfen:
   ```bash
   docker logout ghcr.io && docker pull ghcr.io/skiweg1985/ssa:2.0.1-rc.1
   ```
5. Aufräumen: Release, Tag und die Image-Version auf der Paketseite löschen.

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

**Kein Release, obwohl der Tag gepusht wurde:**
Wahrscheinlich ist der Job **Container-Image (GHCR)** fehlgeschlagen –
`build-and-release` hängt per `needs` daran und startet dann gar nicht erst.
Im Actions-Log den Image-Job ansehen. Nach einem Fix reicht meist „Re-run failed
jobs": der Build-Cache macht den Wiederholungslauf schnell, die teure
arm64-Ebene wird nicht neu gebaut.

**`docker pull` sagt `denied` oder `unauthorized`:**
Das GHCR-Paket ist noch privat. Einmalig auf *public* stellen – siehe
[Container-Image → Einrichtung](#einrichtung-einmalig-vor-dem-ersten-echten-release).

**Image-Tags fehlen, obwohl der Push lief:**
Der Git-Tag ist kein gültiges SemVer (z.B. `v2024.1`). Im Log steht dann eine
Warnung von `docker/metadata-action`. Tag löschen und dreiteilig neu setzen.
