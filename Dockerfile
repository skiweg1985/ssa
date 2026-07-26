# ==============================================================================
# Synology Space Analyzer - Container-Image
#
# Multi-Stage-Build:
#   Stage 1 baut das React-Frontend aus dem Quellcode (tsc + vite),
#   Stage 2 ist die schlanke Python-Runtime mit Backend + gebautem Frontend.
#
# Build:  docker build -t ssa .
# Run:    docker run -p 8080:8080 -v ssa-data:/app/data ssa
#         (Zugangsdaten legst du beim ersten Aufruf im Browser an)
# ==============================================================================

# ---------- Stage 1: Frontend-Build ----------
# Node 22 LTS: Vite 7 verlangt ^20.19.0 || >=22.12.0, und Node 20 ist seit
# April 2026 aus dem Support.
#
# --platform=$BUILDPLATFORM: NICHT entfernen. Beim Multi-Arch-Build im Release
# (linux/amd64 + linux/arm64) wuerde diese Stage sonst zweimal laufen - die
# arm64-Variante unter QEMU-Emulation, wo "npm ci && vite build" leicht
# 15-25 Minuten braucht. Das Ergebnis sind statische JS/CSS-Dateien, also
# architekturunabhaengig; $BUILDPLATFORM heftet die Stage an die Architektur
# des Builders, sie laeuft damit genau einmal nativ.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python-Runtime ----------
# Bewusst OHNE --platform: diese Stage installiert architekturspezifische
# Wheels und muss pro Zielplattform einmal laufen.
FROM python:3.11-slim

# Keine .pyc-Dateien, ungepuffertes Logging (Container-freundlich)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Bewusst NUR requirements.txt (Runtime): Test-Werkzeug steht in
# requirements-dev.txt und hat in einem Produktions-Image nichts verloren.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend + Synology-API-Client
COPY app/ ./app/
COPY explore_syno_api.py ./

# Frisch gebautes Frontend aus Stage 1 (Backend erwartet frontend/dist neben app/)
COPY --from=frontend-build /build/dist ./frontend/dist

# Persistente Daten (SQLite-Historie, Jobs, verschluesselte Creds, secret.key)
# -> als Volume mounten, sonst gehen sie beim Container-Neubau verloren
RUN mkdir -p /app/data

# Unprivilegierter Benutzer mit FIXER UID/GID 1000 - fix, damit die Rechte auf
# gemounteten Volumes vorhersagbar sind.
#
# WICHTIG bei bestehenden Installationen: Ein bereits vorhandenes Datenvolume
# gehoert noch root und muss einmalig uebereignet werden, sonst kann die App
# secret.key/history.db nicht mehr schreiben:
#   docker compose down
#   docker run --rm -v ssa_ssa-data:/data alpine chown -R 1000:1000 /data
#   docker compose up -d
RUN groupadd --gid 1000 ssa \
    && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin ssa \
    && chown -R ssa:ssa /app

VOLUME /app/data

USER ssa

EXPOSE 8080

# Healthcheck ueber den offenen /health-Endpoint (kein curl im slim-Image noetig)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status == 200 else 1)"]

# WICHTIG: genau EIN Worker.
#
# Scheduler, Doppelstart-Schutz fuer Scans und das Login-Rate-Limit leben im
# Prozessspeicher. Mit mehreren Workern plant JEDER Prozess dieselben Jobs ein
# (ein Job laeuft dann n-fach parallel gegen dasselbe NAS), CRUD ueber die API
# erreicht nur den annehmenden Worker, und das Login-Limit gilt effektiv n-fach.
# Aus demselben Grund darf der Container nicht repliziert werden
# (kein "docker compose up --scale").
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
