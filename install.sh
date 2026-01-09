#!/bin/bash
#
# Installations-Script für Synology Space Analyzer als systemd-Service
# Installiert den FastAPI-Service auf einem Debian/Ubuntu-System
#

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfigurierbare Variablen
SERVICE_USER="syno-analyzer"
INSTALL_DIR="/opt/syno-space-analyzer"
SERVICE_NAME="syno-space-analyzer"
PORT="8080"
HOST="0.0.0.0"
LOG_DIR="/var/log/syno-space-analyzer"
VENV_DIR="${INSTALL_DIR}/venv"

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

check_os() {
    if [[ ! -f /etc/debian_version ]] && [[ ! -f /etc/lsb-release ]]; then
        log_error "Dieses Script ist nur für Debian/Ubuntu-Systeme gedacht"
        exit 1
    fi
    log_info "OS-Check erfolgreich: Debian/Ubuntu erkannt"
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 ist nicht installiert. Bitte installieren Sie Python 3:"
        echo "  apt-get update && apt-get install -y python3 python3-venv python3-pip"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_info "Python 3 gefunden: ${PYTHON_VERSION}"
}

check_systemd() {
    if ! command -v systemctl &> /dev/null; then
        log_error "systemd ist nicht verfügbar"
        exit 1
    fi
    log_info "systemd gefunden"
}

# Benutzer erstellen
create_user() {
    if id "$SERVICE_USER" &>/dev/null; then
        log_warning "Benutzer ${SERVICE_USER} existiert bereits"
    else
        log_info "Erstelle Benutzer ${SERVICE_USER}..."
        useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
        log_success "Benutzer ${SERVICE_USER} erstellt"
    fi
}

# Installationsverzeichnis erstellen
create_install_dir() {
    log_info "Erstelle Installationsverzeichnis ${INSTALL_DIR}..."
    
    if [[ -d "$INSTALL_DIR" ]]; then
        log_warning "Installationsverzeichnis ${INSTALL_DIR} existiert bereits"
        read -p "Möchten Sie die vorhandene Installation überschreiben? (j/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Jj]$ ]]; then
            log_error "Installation abgebrochen"
            exit 1
        fi
        log_info "Sichere vorhandene Installation..."
        BACKUP_DIR="${INSTALL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
        mv "$INSTALL_DIR" "$BACKUP_DIR"
        log_info "Backup erstellt: ${BACKUP_DIR}"
    fi
    
    mkdir -p "$INSTALL_DIR"
    log_success "Installationsverzeichnis erstellt"
}

# Projekt-Dateien kopieren
copy_project_files() {
    log_info "Kopiere Projekt-Dateien..."
    
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Wichtige Dateien und Verzeichnisse kopieren
    cp -r "${SCRIPT_DIR}/app" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/README.md" "${INSTALL_DIR}/" 2>/dev/null || true
    
    # config.yaml.example kopieren, falls vorhanden
    if [[ -f "${SCRIPT_DIR}/config.yaml.example" ]]; then
        cp "${SCRIPT_DIR}/config.yaml.example" "${INSTALL_DIR}/"
        log_info "config.yaml.example kopiert - bitte erstellen Sie config.yaml"
    fi
    
    # .env.example kopieren, falls vorhanden
    if [[ -f "${SCRIPT_DIR}/.env.example" ]]; then
        cp "${SCRIPT_DIR}/.env.example" "${INSTALL_DIR}/"
        log_info ".env.example kopiert - bitte erstellen Sie .env falls benötigt"
    fi
    
    log_success "Projekt-Dateien kopiert"
}

# Virtuelles Environment erstellen
create_venv() {
    log_info "Erstelle virtuelles Python-Environment..."
    
    python3 -m venv "$VENV_DIR"
    log_success "Virtuelles Environment erstellt"
}

# Abhängigkeiten installieren
install_dependencies() {
    log_info "Installiere Python-Abhängigkeiten..."
    
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
    
    log_success "Abhängigkeiten installiert"
}

# Log-Verzeichnis erstellen
create_log_dir() {
    log_info "Erstelle Log-Verzeichnis ${LOG_DIR}..."
    
    mkdir -p "$LOG_DIR"
    chown "${SERVICE_USER}:${SERVICE_USER}" "$LOG_DIR"
    chmod 755 "$LOG_DIR"
    
    log_success "Log-Verzeichnis erstellt"
}

# Permissions setzen
set_permissions() {
    log_info "Setze Dateiberechtigungen..."
    
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "$INSTALL_DIR"
    chmod -R 755 "$INSTALL_DIR"
    
    log_success "Dateiberechtigungen gesetzt"
}

# systemd-Service erstellen
create_systemd_service() {
    log_info "Erstelle systemd-Service..."
    
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
    
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Synology Space Analyzer API Service
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host ${HOST} --port ${PORT}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF
    
    log_success "systemd-Service-Datei erstellt: ${SERVICE_FILE}"
}

# Service aktivieren und starten
enable_and_start_service() {
    log_info "Lade systemd-Daemon neu..."
    systemctl daemon-reload
    
    log_info "Aktiviere Service ${SERVICE_NAME}..."
    systemctl enable "${SERVICE_NAME}.service"
    
    log_info "Starte Service ${SERVICE_NAME}..."
    systemctl start "${SERVICE_NAME}.service"
    
    # Kurz warten, damit Service starten kann
    sleep 2
    
    # Status prüfen
    if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        log_success "Service ${SERVICE_NAME} läuft erfolgreich"
    else
        log_error "Service ${SERVICE_NAME} konnte nicht gestartet werden"
        log_info "Zeige Service-Status:"
        systemctl status "${SERVICE_NAME}.service" || true
        exit 1
    fi
}

# Zusammenfassung anzeigen
show_summary() {
    echo ""
    log_success "=========================================="
    log_success "Installation erfolgreich abgeschlossen!"
    log_success "=========================================="
    echo ""
    echo "Service-Informationen:"
    echo "  Service-Name: ${SERVICE_NAME}"
    echo "  Installationsverzeichnis: ${INSTALL_DIR}"
    echo "  Benutzer: ${SERVICE_USER}"
    echo "  Port: ${PORT}"
    echo "  URL: http://${HOST}:${PORT}"
    echo ""
    echo "Nützliche Befehle:"
    echo "  Service-Status:    systemctl status ${SERVICE_NAME}"
    echo "  Service stoppen:   systemctl stop ${SERVICE_NAME}"
    echo "  Service starten:   systemctl start ${SERVICE_NAME}"
    echo "  Service neu starten: systemctl restart ${SERVICE_NAME}"
    echo "  Logs anzeigen:     journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo "Wichtige Hinweise:"
    echo "  - Stellen Sie sicher, dass config.yaml im Installationsverzeichnis existiert"
    echo "  - Prüfen Sie die Logs bei Problemen: journalctl -u ${SERVICE_NAME}"
    echo ""
}

# Hauptfunktion
main() {
    log_info "Starte Installation von ${SERVICE_NAME}..."
    echo ""
    
    check_root
    check_os
    check_python
    check_systemd
    
    create_user
    create_install_dir
    copy_project_files
    create_venv
    install_dependencies
    create_log_dir
    set_permissions
    create_systemd_service
    enable_and_start_service
    
    show_summary
}

# Script ausführen
main "$@"
