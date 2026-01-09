#!/bin/bash
#
# Service-Management-Wrapper für Synology Space Analyzer
# Vereinfachte Befehle zum Verwalten des systemd-Services
#

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Service-Name (muss mit install.sh übereinstimmen)
SERVICE_NAME="syno-space-analyzer"

# Funktionen
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Prüft ob Service existiert
check_service() {
    if ! systemctl list-unit-files | grep -q "${SERVICE_NAME}.service"; then
        log_error "Service ${SERVICE_NAME} ist nicht installiert"
        echo "Bitte führen Sie zuerst ./install.sh aus"
        exit 1
    fi
}

# Service starten
start_service() {
    check_service
    log_info "Starte Service ${SERVICE_NAME}..."
    
    if sudo systemctl start "${SERVICE_NAME}.service"; then
        log_success "Service gestartet"
        show_status
    else
        log_error "Service konnte nicht gestartet werden"
        exit 1
    fi
}

# Service stoppen
stop_service() {
    check_service
    log_info "Stoppe Service ${SERVICE_NAME}..."
    
    if sudo systemctl stop "${SERVICE_NAME}.service"; then
        log_success "Service gestoppt"
    else
        log_error "Service konnte nicht gestoppt werden"
        exit 1
    fi
}

# Service neu starten
restart_service() {
    check_service
    log_info "Starte Service ${SERVICE_NAME} neu..."
    
    if sudo systemctl restart "${SERVICE_NAME}.service"; then
        log_success "Service neu gestartet"
        sleep 1
        show_status
    else
        log_error "Service konnte nicht neu gestartet werden"
        exit 1
    fi
}

# Service-Status anzeigen
show_status() {
    check_service
    echo ""
    log_info "Service-Status:"
    echo ""
    sudo systemctl status "${SERVICE_NAME}.service" --no-pager || true
    echo ""
}

# Logs anzeigen
show_logs() {
    check_service
    
    if [[ "${1:-}" == "-f" ]] || [[ "${1:-}" == "--follow" ]]; then
        log_info "Zeige Logs (Live-Modus, Ctrl+C zum Beenden)..."
        echo ""
        sudo journalctl -u "${SERVICE_NAME}.service" -f
    else
        log_info "Zeige letzte Log-Einträge..."
        echo ""
        sudo journalctl -u "${SERVICE_NAME}.service" -n 50 --no-pager
        echo ""
        echo "Für Live-Logs verwenden Sie: $0 logs -f"
    fi
}

# Hilfe anzeigen
show_help() {
    cat <<EOF
Verwendung: $0 <Befehl> [Optionen]

Befehle:
  start              Service starten
  stop               Service stoppen
  restart            Service neu starten
  status             Service-Status anzeigen
  logs [--follow]    Logs anzeigen (--follow für Live-Modus)
  help               Diese Hilfe anzeigen

Beispiele:
  $0 start                    # Service starten
  $0 stop                     # Service stoppen
  $0 restart                  # Service neu starten
  $0 status                   # Status anzeigen
  $0 logs                     # Letzte 50 Log-Einträge
  $0 logs --follow            # Live-Logs (wie tail -f)

Hinweis:
  Einige Befehle benötigen sudo-Rechte.
EOF
}

# Hauptfunktion
main() {
    case "${1:-help}" in
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "${2:-}"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unbekannter Befehl: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Script ausführen
main "$@"
