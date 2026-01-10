#!/bin/bash
# Systemd Service Installer für Synology Space Analyzer
# Verwendet das Projektverzeichnis direkt (kein separates Install-Verzeichnis)

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
HOST="${HOST:-0.0.0.0}"

# Projektverzeichnis (wo das Script ausgeführt wird)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Prüfe Debian/Ubuntu
check_distro() {
    if [[ ! -f /etc/debian_version ]] && [[ ! -f /etc/lsb-release ]]; then
        log_warning "Dieses Script wurde für Debian/Ubuntu entwickelt"
    fi
}

# Prüfe Python 3
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 ist nicht installiert"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_info "Python Version: $PYTHON_VERSION"
}

# Prüfe systemd
check_systemd() {
    if ! command -v systemctl &> /dev/null; then
        log_error "systemd ist nicht verfügbar"
        exit 1
    fi
}

# Konfiguriere Port
configure_port() {
    if [[ -n "${PORT:-}" ]]; then
        log_info "Port aus Umgebungsvariable: $PORT"
        return 0
    fi
    
    echo
    log_info "Konfiguriere Server-Port..."
    read -p "Port für den Server (Standard: 8080): " input_port
    
    if [[ -z "$input_port" ]]; then
        PORT=8080
    else
        # Validiere Port-Nummer
        if [[ "$input_port" =~ ^[0-9]+$ ]] && [[ "$input_port" -ge 1 ]] && [[ "$input_port" -le 65535 ]]; then
            PORT="$input_port"
        else
            log_error "Ungültige Port-Nummer: $input_port"
            exit 1
        fi
    fi
    
    log_success "Port konfiguriert: $PORT"
}

# Prüfe und erstelle config.yaml
check_config() {
    local config_file="$PROJECT_DIR/config.yaml"
    local example_file="$PROJECT_DIR/config.yaml.example"
    
    if [[ -f "$config_file" ]]; then
        log_info "config.yaml existiert bereits"
        return 0
    fi
    
    if [[ ! -f "$example_file" ]]; then
        log_warning "config.yaml.example nicht gefunden - überspringe Config-Prüfung"
        return 0
    fi
    
    echo
    log_warning "config.yaml nicht gefunden"
    read -p "config.yaml.example nach config.yaml kopieren? (J/n): " -n 1 -r
    echo
    
    if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[JjYy]$ ]]; then
        log_info "Kopiere config.yaml.example nach config.yaml..."
        cp "$example_file" "$config_file" || {
            log_error "Fehler beim Kopieren der Config-Datei"
            exit 1
        }
        log_success "config.yaml erstellt"
        log_warning "Bitte passe config.yaml an deine Bedürfnisse an!"
    else
        log_info "Überspringe Erstellung von config.yaml"
        log_warning "Der Server benötigt eine config.yaml zum Betrieb"
    fi
}

# Erstelle Service-Benutzer
create_user() {
    if id "$SERVICE_USER" &>/dev/null; then
        log_info "Benutzer '$SERVICE_USER' existiert bereits"
    else
        log_info "Erstelle Benutzer '$SERVICE_USER'..."
        useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" || {
            log_error "Fehler beim Erstellen des Benutzers"
            exit 1
        }
        log_success "Benutzer '$SERVICE_USER' erstellt"
    fi
}

# Erstelle virtuelles Environment
create_venv() {
    local venv_path="$PROJECT_DIR/venv"
    
    if [[ -d "$venv_path" ]]; then
        log_warning "Virtuelles Environment existiert bereits in $venv_path"
        read -p "Neu erstellen? (j/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Jj]$ ]]; then
            log_info "Entferne vorhandenes virtuelles Environment..."
            rm -rf "$venv_path"
        else
            log_info "Verwende vorhandenes virtuelles Environment"
            return 0
        fi
    fi
    
    log_info "Erstelle virtuelles Environment in $venv_path..."
    python3 -m venv "$venv_path" || {
        log_error "Fehler beim Erstellen des virtuellen Environments"
        exit 1
    }
    
    log_success "Virtuelles Environment erstellt"
}

# Installiere Abhängigkeiten
install_dependencies() {
    local venv_path="$PROJECT_DIR/venv"
    local requirements_file="$PROJECT_DIR/requirements.txt"
    
    if [[ ! -f "$requirements_file" ]]; then
        log_error "requirements.txt nicht gefunden in $PROJECT_DIR"
        exit 1
    fi
    
    log_info "Installiere Python-Abhängigkeiten..."
    "$venv_path/bin/pip" install --upgrade pip || {
        log_error "Fehler beim Aktualisieren von pip"
        exit 1
    }
    
    "$venv_path/bin/pip" install -r "$requirements_file" || {
        log_error "Fehler beim Installieren der Abhängigkeiten"
        exit 1
    }
    
    log_success "Abhängigkeiten installiert"
}

# Erstelle data-Verzeichnis
create_data_dir() {
    local data_dir="$PROJECT_DIR/data"
    
    if [[ ! -d "$data_dir" ]]; then
        log_info "Erstelle data-Verzeichnis..."
        mkdir -p "$data_dir"
    fi
    
    # Setze Permissions
    chown -R "$SERVICE_USER:$SERVICE_USER" "$data_dir" || {
        log_warning "Konnte Permissions für $data_dir nicht setzen"
    }
    
    log_success "Data-Verzeichnis bereit"
}

# Erstelle systemd Service-Datei
create_service_file() {
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    local venv_path="$PROJECT_DIR/venv"
    local python_path="$venv_path/bin"
    local uvicorn_path="$venv_path/bin/uvicorn"
    
    log_info "Erstelle systemd Service-Datei..."
    
    cat > "$service_file" <<EOF
[Unit]
Description=Synology Space Analyzer API Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$python_path"
ExecStart=$uvicorn_path app.main:app --host $HOST --port $PORT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# Umgebungsvariablen (optional)
# Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF
    
    log_success "Service-Datei erstellt: $service_file"
}

# Setze Permissions für Projektverzeichnis
set_permissions() {
    log_info "Setze Permissions für Projektverzeichnis..."
    
    # Setze Besitzer für Projektverzeichnis (außer venv, das bleibt beim aktuellen Benutzer)
    chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR" || {
        log_warning "Konnte Permissions nicht vollständig setzen"
    }
    
    # Stelle sicher, dass venv lesbar ist
    if [[ -d "$PROJECT_DIR/venv" ]]; then
        chmod -R u+rX "$PROJECT_DIR/venv" || true
    fi
    
    # Stelle sicher, dass Scripts ausführbar sind
    find "$PROJECT_DIR" -name "*.sh" -type f -exec chmod +x {} \; || true
    
    log_success "Permissions gesetzt"
}

# Aktiviere und starte Service
enable_service() {
    log_info "Lade systemd-Daemon neu..."
    systemctl daemon-reload || {
        log_error "Fehler beim Neuladen des systemd-Daemons"
        exit 1
    }
    
    log_info "Aktiviere Service '$SERVICE_NAME'..."
    systemctl enable "$SERVICE_NAME" || {
        log_error "Fehler beim Aktivieren des Services"
        exit 1
    }
    
    log_info "Starte Service '$SERVICE_NAME'..."
    systemctl start "$SERVICE_NAME" || {
        log_error "Fehler beim Starten des Services"
        exit 1
    }
    
    log_success "Service gestartet"
}

# Prüfe Service-Status
check_service_status() {
    log_info "Prüfe Service-Status..."
    sleep 2
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service läuft erfolgreich"
    else
        log_error "Service läuft nicht!"
        log_info "Zeige Service-Status:"
        systemctl status "$SERVICE_NAME" --no-pager || true
        exit 1
    fi
}

# Zeige Informationen
show_info() {
    echo
    log_success "Installation abgeschlossen!"
    echo
    echo "Projektverzeichnis: $PROJECT_DIR"
    echo "Service-Name: $SERVICE_NAME"
    echo "Benutzer: $SERVICE_USER"
    echo "Port: $PORT"
    echo
    echo "Nützliche Befehle:"
    echo "  Status anzeigen:  systemctl status $SERVICE_NAME"
    echo "  Logs anzeigen:    journalctl -u $SERVICE_NAME -f"
    echo "  Service stoppen:  systemctl stop $SERVICE_NAME"
    echo "  Service starten:  systemctl start $SERVICE_NAME"
    echo "  Service neu starten: systemctl restart $SERVICE_NAME"
    echo
}

# Hauptfunktion
main() {
    log_info "Starte Installation von $SERVICE_NAME..."
    echo
    
    check_root
    check_distro
    check_python
    check_systemd
    
    configure_port
    check_config
    
    create_user
    create_venv
    install_dependencies
    create_data_dir
    create_service_file
    set_permissions
    enable_service
    check_service_status
    show_info
}

# Führe Installation aus
main "$@"
