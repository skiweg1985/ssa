#!/usr/bin/env bash
# ==============================================================================
# Synology Space Analyzer - Entwicklungsumgebung
#
#   ./dev.sh setup     Einmalig: venv, Python- und npm-Pakete, Frontend bauen
#   ./dev.sh           Backend und Vite-Dev-Server parallel starten
#   ./dev.sh backend   nur das Backend (Port 8080)
#   ./dev.sh frontend  nur den Vite-Dev-Server (Port 5173)
#   ./dev.sh build     Frontend neu bauen (fuer die UI unter Port 8080)
#   ./dev.sh test      Testsuite
#
# Fuer den BETRIEB ist dieses Skript nicht gedacht - dafuer gibt es
# docker compose bzw. das Release-Paket mit install.sh (siehe README.md).
# ==============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV_DIR=".venv"
BACKEND_PORT="${SSA_DEV_BACKEND_PORT:-8080}"
FRONTEND_PORT="${SSA_DEV_FRONTEND_PORT:-5173}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[FEHLER]${NC} $1" >&2; }

# ------------------------------------------------------------------------------
# Voraussetzungen
# ------------------------------------------------------------------------------

require_python() {
    if ! command -v python3 &>/dev/null; then
        log_error "python3 nicht gefunden - benoetigt wird Python 3.11+"
        exit 1
    fi
}

require_node() {
    if ! command -v npm &>/dev/null; then
        log_error "npm nicht gefunden - benoetigt wird Node 22+"
        echo "  Ohne Node laesst sich das Frontend nicht bauen. Alternativen:"
        echo "    docker compose up -d          (baut das Frontend im Image)"
        echo "    Release-Paket verwenden       (bringt es fertig gebaut mit)"
        exit 1
    fi
}

# Warnt nur, statt abzubrechen: eine aeltere Node-Version baut oft trotzdem,
# und wer bewusst abweicht, soll nicht ausgesperrt werden.
check_node_version() {
    local major
    major="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"
    if [[ -n "$major" ]] && (( major < 22 )); then
        log_warn "Node $major gefunden, Vite 7 erwartet 22+. Build kann fehlschlagen."
    fi
}

# ------------------------------------------------------------------------------
# Befehle
# ------------------------------------------------------------------------------

cmd_setup() {
    require_python
    require_node
    check_node_version

    if [[ ! -d "$VENV_DIR" ]]; then
        log_info "Lege virtuelles Environment an ($VENV_DIR)..."
        python3 -m venv "$VENV_DIR"
    else
        log_info "Verwende vorhandenes $VENV_DIR"
    fi

    log_info "Installiere Python-Pakete (inkl. Test-Werkzeug)..."
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r requirements-dev.txt

    log_info "Installiere npm-Pakete..."
    npm --prefix frontend ci --silent

    cmd_build

    if [[ ! -f config.yaml && -f config.yaml.example ]]; then
        log_warn "Keine config.yaml vorhanden."
        echo "  Optional fuer den Erst-Import von Scans:  cp config.yaml.example config.yaml"
        echo "  Scan-Jobs lassen sich aber auch komplett im Frontend anlegen."
    fi
    if [[ -z "${SSA_ADMIN_PASSWORD:-}" && ! -f .env ]]; then
        log_info "Kein Admin-Passwort gesetzt - das ist der Normalfall."
        echo "  Beim ersten Aufruf der Oberflaeche legst du das Konto im Browser an."
    fi

    echo
    log_success "Setup abgeschlossen. Weiter mit: ./dev.sh"
}

cmd_build() {
    require_node
    log_info "Baue Frontend..."
    # Ausgabe bewusst sichtbar: tsc-Fehler wuerden sonst untergehen
    npm --prefix frontend run build
    log_success "Frontend gebaut (frontend/dist)"
}

# Prueft vor dem Backend-Start, ob ueberhaupt eine UI ausgeliefert werden kann.
# frontend/dist ist nicht versioniert, in einem frischen Klon fehlt es also.
warn_if_no_build() {
    if [[ ! -f frontend/dist/index.html ]]; then
        log_warn "Kein Frontend-Build - Port $BACKEND_PORT liefert nur eine Hinweisseite."
        echo "  Bauen mit: ./dev.sh build     (oder ./dev.sh frontend fuer den Dev-Server)"
    fi
}

ensure_venv() {
    if [[ ! -x "$VENV_DIR/bin/uvicorn" ]]; then
        log_error "Kein einsatzbereites $VENV_DIR gefunden - bitte zuerst: ./dev.sh setup"
        exit 1
    fi
}

cmd_backend() {
    ensure_venv
    warn_if_no_build
    log_info "Backend auf http://localhost:$BACKEND_PORT (Reload aktiv)"
    exec "$VENV_DIR/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT"
}

cmd_frontend() {
    require_node
    log_info "Vite auf http://localhost:$FRONTEND_PORT (proxyt /api auf :$BACKEND_PORT)"
    exec npm --prefix frontend run dev
}

cmd_test() {
    ensure_venv
    exec "$VENV_DIR/bin/pytest" -q "$@"
}

# Beide Server gleichzeitig. Der Vite-Dev-Server auf 5173 ist die Adresse zum
# Arbeiten (Hot Reload); 8080 zeigt den gebauten Stand.

BACKEND_PID=""
FRONTEND_PID=""

# Beendet beide Server samt ihrer Kindprozesse.
#
# Die PIDs werden einzeln adressiert statt per "kill 0": Letzteres trifft die
# Prozessgruppe, und die ist nicht verlaesslich dieselbe - wird das Skript
# nicht aus einer interaktiven Shell gestartet, blieben beide Server als
# Waisen zurueck und hielten ihre Ports besetzt.
#
# pkill -P zuerst, weil "npm run dev" den eigentlichen vite-Prozess als Kind
# startet; nur npm zu beenden liesse vite weiterlaufen.
cleanup_servers() {
    trap - INT TERM EXIT
    local pid
    for pid in $BACKEND_PID $FRONTEND_PID; do
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}

cmd_start() {
    ensure_venv
    require_node
    warn_if_no_build

    trap cleanup_servers INT TERM EXIT

    "$VENV_DIR/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT" &
    BACKEND_PID=$!
    npm --prefix frontend run dev &
    FRONTEND_PID=$!

    echo
    log_success "Frontend (Hot Reload): http://localhost:$FRONTEND_PORT"
    log_info    "Backend / gebaute UI:  http://localhost:$BACKEND_PORT"
    echo "  Beenden mit Strg-C"
    echo

    wait
}

usage() {
    sed -n '3,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

case "${1:-start}" in
    setup)          cmd_setup ;;
    build)          cmd_build ;;
    backend)        cmd_backend ;;
    frontend)       cmd_frontend ;;
    test)           shift; cmd_test "$@" ;;
    start)          cmd_start ;;
    -h|--help|help) usage ;;
    *)
        log_error "Unbekannter Befehl: $1"
        echo
        usage
        exit 1
        ;;
esac
