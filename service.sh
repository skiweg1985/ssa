#!/bin/bash
# Service-Management-Wrapper für Synology Space Analyzer

set -euo pipefail

# Konfiguration
SERVICE_NAME="${SERVICE_NAME:-syno-space-analyzer}"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Prüfe ob systemctl verfügbar ist
if ! command -v systemctl &> /dev/null; then
    echo -e "${RED}Fehler: systemctl ist nicht verfügbar${NC}"
    exit 1
fi

# Funktionen
show_usage() {
    echo "Verwendung: $0 {start|stop|restart|status|logs|enable|disable}"
    echo
    echo "Befehle:"
    echo "  start    - Service starten"
    echo "  stop     - Service stoppen"
    echo "  restart  - Service neu starten"
    echo "  status   - Service-Status anzeigen"
    echo "  logs     - Logs anzeigen (mit -f für Follow-Modus)"
    echo "  enable   - Service aktivieren (Start bei Boot)"
    echo "  disable  - Service deaktivieren"
    exit 1
}

# Service starten
start_service() {
    echo -e "${BLUE}Starte Service '$SERVICE_NAME'...${NC}"
    sudo systemctl start "$SERVICE_NAME"
    sleep 1
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}Service gestartet${NC}"
    else
        echo -e "${RED}Fehler beim Starten des Services${NC}"
        exit 1
    fi
}

# Service stoppen
stop_service() {
    echo -e "${BLUE}Stoppe Service '$SERVICE_NAME'...${NC}"
    sudo systemctl stop "$SERVICE_NAME"
    sleep 1
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}Service gestoppt${NC}"
    else
        echo -e "${RED}Fehler beim Stoppen des Services${NC}"
        exit 1
    fi
}

# Service neu starten
restart_service() {
    echo -e "${BLUE}Starte Service '$SERVICE_NAME' neu...${NC}"
    sudo systemctl restart "$SERVICE_NAME"
    sleep 1
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}Service neu gestartet${NC}"
    else
        echo -e "${RED}Fehler beim Neustarten des Services${NC}"
        exit 1
    fi
}

# Service-Status anzeigen
show_status() {
    echo -e "${BLUE}Status von '$SERVICE_NAME':${NC}"
    echo
    systemctl status "$SERVICE_NAME" --no-pager -l || true
}

# Logs anzeigen
show_logs() {
    local follow=false
    
    # Prüfe ob -f Flag gesetzt ist
    if [[ "${2:-}" == "-f" ]] || [[ "${2:-}" == "--follow" ]]; then
        follow=true
    fi
    
    if [[ "$follow" == true ]]; then
        echo -e "${BLUE}Zeige Logs von '$SERVICE_NAME' (Follow-Modus, Ctrl+C zum Beenden)...${NC}"
        sudo journalctl -u "$SERVICE_NAME" -f
    else
        echo -e "${BLUE}Zeige letzte Logs von '$SERVICE_NAME':${NC}"
        sudo journalctl -u "$SERVICE_NAME" -n 50 --no-pager
    fi
}

# Service aktivieren
enable_service() {
    echo -e "${BLUE}Aktiviere Service '$SERVICE_NAME' (Start bei Boot)...${NC}"
    sudo systemctl enable "$SERVICE_NAME"
    echo -e "${GREEN}Service aktiviert${NC}"
}

# Service deaktivieren
disable_service() {
    echo -e "${BLUE}Deaktiviere Service '$SERVICE_NAME'...${NC}"
    sudo systemctl disable "$SERVICE_NAME"
    echo -e "${GREEN}Service deaktiviert${NC}"
}

# Hauptlogik
case "${1:-}" in
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
        show_logs "$@"
        ;;
    enable)
        enable_service
        ;;
    disable)
        disable_service
        ;;
    *)
        show_usage
        ;;
esac
