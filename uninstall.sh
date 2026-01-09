#!/bin/bash
# Systemd Service Deinstaller für Synology Space Analyzer

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfiguration
SERVICE_USER="${SERVICE_USER:-syno-analyzer}"
SERVICE_NAME="${SERVICE_NAME:-syno-space-analyzer}"

# Log-Funktionen
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Prüfe Root-Rechte
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Dieses Script muss als root ausgeführt werden (sudo)"
        exit 1
    fi
}

# Stoppe und deaktiviere Service
stop_service() {
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "Stoppe Service '$SERVICE_NAME'..."
        systemctl stop "$SERVICE_NAME" || {
            log_warning "Fehler beim Stoppen des Services"
        }
    else
        log_info "Service '$SERVICE_NAME' läuft nicht"
    fi
    
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "Deaktiviere Service '$SERVICE_NAME'..."
        systemctl disable "$SERVICE_NAME" || {
            log_warning "Fehler beim Deaktivieren des Services"
        }
    else
        log_info "Service '$SERVICE_NAME' ist nicht aktiviert"
    fi
}

# Entferne Service-Datei
remove_service_file() {
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    
    if [[ -f "$service_file" ]]; then
        log_info "Entferne Service-Datei: $service_file"
        rm -f "$service_file"
        systemctl daemon-reload
        log_success "Service-Datei entfernt"
    else
        log_info "Service-Datei nicht gefunden: $service_file"
    fi
}

# Entferne Benutzer (optional)
remove_user() {
    if id "$SERVICE_USER" &>/dev/null; then
        read -p "Benutzer '$SERVICE_USER' entfernen? (j/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Jj]$ ]]; then
            log_info "Entferne Benutzer '$SERVICE_USER'..."
            userdel "$SERVICE_USER" 2>/dev/null || {
                log_warning "Konnte Benutzer '$SERVICE_USER' nicht entfernen (möglicherweise noch in Verwendung)"
            }
            log_success "Benutzer entfernt"
        else
            log_info "Benutzer '$SERVICE_USER' bleibt erhalten"
        fi
    else
        log_info "Benutzer '$SERVICE_USER' existiert nicht"
    fi
}

# Hauptfunktion
main() {
    log_info "Starte Deinstallation von $SERVICE_NAME..."
    echo
    
    check_root
    
    stop_service
    remove_service_file
    
    echo
    log_warning "Hinweis: Projekt-Dateien und virtuelles Environment werden NICHT entfernt"
    log_info "Diese müssen manuell gelöscht werden, falls gewünscht"
    echo
    
    remove_user
    
    echo
    log_success "Deinstallation abgeschlossen!"
    echo
}

# Führe Deinstallation aus
main "$@"
