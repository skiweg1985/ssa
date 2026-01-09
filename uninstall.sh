#!/bin/bash
#
# Deinstallations-Script für Synology Space Analyzer systemd-Service
# Entfernt den Service und optional alle zugehörigen Dateien
#

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfigurierbare Variablen (müssen mit install.sh übereinstimmen)
SERVICE_USER="syno-analyzer"
INSTALL_DIR="/opt/syno-space-analyzer"
SERVICE_NAME="syno-space-analyzer"
LOG_DIR="/var/log/syno-space-analyzer"

# Funktionen
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

# Prüfungen
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Dieses Script muss als root ausgeführt werden (sudo)"
        exit 1
    fi
}

# Service stoppen und deaktivieren
stop_service() {
    if systemctl list-unit-files | grep -q "${SERVICE_NAME}.service"; then
        log_info "Stoppe Service ${SERVICE_NAME}..."
        
        if systemctl is-active --quiet "${SERVICE_NAME}.service" 2>/dev/null; then
            systemctl stop "${SERVICE_NAME}.service"
            log_success "Service gestoppt"
        else
            log_warning "Service war bereits gestoppt"
        fi
        
        log_info "Deaktiviere Service ${SERVICE_NAME}..."
        systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true
        log_success "Service deaktiviert"
    else
        log_warning "Service ${SERVICE_NAME} ist nicht installiert"
    fi
}

# Service-Datei entfernen
remove_service_file() {
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    
    if [[ -f "$SERVICE_FILE" ]]; then
        log_info "Entferne Service-Datei ${SERVICE_FILE}..."
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        log_success "Service-Datei entfernt"
    else
        log_warning "Service-Datei ${SERVICE_FILE} existiert nicht"
    fi
}

# Installationsverzeichnis entfernen
remove_install_dir() {
    if [[ -d "$INSTALL_DIR" ]]; then
        read -p "Möchten Sie das Installationsverzeichnis ${INSTALL_DIR} entfernen? (j/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Jj]$ ]]; then
            log_info "Entferne Installationsverzeichnis ${INSTALL_DIR}..."
            rm -rf "$INSTALL_DIR"
            log_success "Installationsverzeichnis entfernt"
        else
            log_info "Installationsverzeichnis ${INSTALL_DIR} bleibt erhalten"
        fi
    else
        log_warning "Installationsverzeichnis ${INSTALL_DIR} existiert nicht"
    fi
}

# Log-Verzeichnis entfernen
remove_log_dir() {
    if [[ -d "$LOG_DIR" ]]; then
        read -p "Möchten Sie das Log-Verzeichnis ${LOG_DIR} entfernen? (j/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Jj]$ ]]; then
            log_info "Entferne Log-Verzeichnis ${LOG_DIR}..."
            rm -rf "$LOG_DIR"
            log_success "Log-Verzeichnis entfernt"
        else
            log_info "Log-Verzeichnis ${LOG_DIR} bleibt erhalten"
        fi
    else
        log_warning "Log-Verzeichnis ${LOG_DIR} existiert nicht"
    fi
}

# Benutzer entfernen
remove_user() {
    if id "$SERVICE_USER" &>/dev/null; then
        read -p "Möchten Sie den Benutzer ${SERVICE_USER} entfernen? (j/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Jj]$ ]]; then
            log_info "Entferne Benutzer ${SERVICE_USER}..."
            userdel "$SERVICE_USER" 2>/dev/null || true
            log_success "Benutzer entfernt"
        else
            log_info "Benutzer ${SERVICE_USER} bleibt erhalten"
        fi
    else
        log_warning "Benutzer ${SERVICE_USER} existiert nicht"
    fi
}

# Zusammenfassung anzeigen
show_summary() {
    echo ""
    log_success "=========================================="
    log_success "Deinstallation abgeschlossen!"
    log_success "=========================================="
    echo ""
    echo "Der Service wurde erfolgreich entfernt."
    echo ""
    echo "Hinweis:"
    echo "  - Installationsverzeichnis: ${INSTALL_DIR}"
    echo "  - Log-Verzeichnis: ${LOG_DIR}"
    echo "  - Benutzer: ${SERVICE_USER}"
    echo ""
    echo "Diese wurden nur entfernt, wenn Sie dies bestätigt haben."
    echo ""
}

# Hauptfunktion
main() {
    log_info "Starte Deinstallation von ${SERVICE_NAME}..."
    echo ""
    
    check_root
    
    stop_service
    remove_service_file
    remove_install_dir
    remove_log_dir
    remove_user
    
    show_summary
}

# Script ausführen
main "$@"
