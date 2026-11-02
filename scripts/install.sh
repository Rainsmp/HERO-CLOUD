#!/usr/bin/env bash
set -Eeuo pipefail

REPO="Rainsmp/HERO-CLOUD"
BRANCH="main"
INSTALL_DIR="/opt/hero-cloud"
SERVICE="hero-cloud"
SERVICE_FILE="/etc/systemd/system/hero-cloud.service"
ENV_FILE="$INSTALL_DIR/.env"
ENV_EXAMPLE="$INSTALL_DIR/.env.example"
TEMP_DIR=""

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}[OK]${RESET} $*"; }
info() { echo -e "${CYAN}[INFO]${RESET} $*"; }
fail() { echo -e "${RED}[ERROR]${RESET} $*"; }

cleanup() {
    [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

require_root() {
    if [[ "$EUID" -ne 0 ]]; then
        fail "Run with sudo:"
        echo "sudo bash <(curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/scripts/install.sh)"
        exit 1
    fi
}

banner() {
    clear 2>/dev/null || true
    echo
    echo "╔══════════════════════════════════════════════╗"
    echo "║                 HERO CLOUD                   ║"
    echo "║             VPS MANAGEMENT SYSTEM            ║"
    echo "╚══════════════════════════════════════════════╝"
    echo
}

download_project() {
    TEMP_DIR="$(mktemp -d)"
    info "Downloading HERO CLOUD source..."

    curl -fL --retry 3 \
        "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" \
        -o "$TEMP_DIR/project.tar.gz"

    tar -xzf "$TEMP_DIR/project.tar.gz" -C "$TEMP_DIR"

    local source_dir="$TEMP_DIR/HERO-CLOUD-$BRANCH"

    [[ -d "$source_dir" ]] || {
        fail "Could not find downloaded project."
        return 1
    }

    mkdir -p "$INSTALL_DIR"

    if [[ -d "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/.env" ]]; then
        cp -a "$INSTALL_DIR/.env" "$TEMP_DIR/existing.env"
    fi

    cp -a "$source_dir/." "$INSTALL_DIR/"

    if [[ -f "$TEMP_DIR/existing.env" ]]; then
        cp "$TEMP_DIR/existing.env" "$INSTALL_DIR/.env"
    fi

    ok "Source files installed in $INSTALL_DIR"
}

read_value() {
    local label="$1"
    local default="$2"
    local result=""

    read -r -p "$label [$default]: " result
    printf '%s' "${result:-$default}"
}

configure_environment() {
    mkdir -p "$INSTALL_DIR"

    if [[ ! -f "$ENV_EXAMPLE" ]]; then
        fail ".env.example is missing."
        return 1
    fi

    local old_token=""
    if [[ -f "$ENV_FILE" ]]; then
        old_token="$(grep '^DISCORD_TOKEN=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
    fi

    echo
    echo "========== DISCORD CONFIGURATION =========="
    echo

    local token="$old_token"

    if [[ -z "$token" || "$token" == "PUT_DISCORD_BOT_TOKEN_HERE" ]]; then
        read -r -s -p "Discord Bot Token: " token
        echo
    else
        read -r -p "Keep existing Discord token? [Y/n]: " answer
        if [[ "${answer,,}" == "n" ]]; then
            read -r -s -p "New Discord Bot Token: " token
            echo
        fi
    fi

    [[ -n "$token" ]] || {
        fail "Discord token is required."
        return 1
    }

    local owners guild max_vps ram cpu disk days lxc

    owners="$(read_value "Owner Discord IDs (comma separated)" "123456789012345678,234567890123456789")"
    guild="$(read_value "Guild IDs (comma separated)" "1563162173256110250,1563162173256110250")"
    max_vps="$(read_value "Maximum VPS count" "100")"
    ram="$(read_value "Default RAM (MB)" "1024")"
    cpu="$(read_value "Default CPU percent" "100")"
    disk="$(read_value "Default disk (MB)" "10240")"
    days="$(read_value "Default VPS duration (days)" "30")"
    lxc="$(read_value "LXC executable path" "/snap/bin/lxc")"

    for number in "$max_vps" "$ram" "$cpu" "$disk" "$days"; do
        [[ "$number" =~ ^[0-9]+$ ]] || {
            fail "Numeric settings must contain numbers only."
            return 1
        }
    done

    [[ "$max_vps" -gt 0 && "$ram" -gt 0 && "$cpu" -gt 0 && "$disk" -gt 0 && "$days" -gt 0 ]] || {
        fail "Numeric settings must be greater than zero."
        return 1
    }

    local tmp_env
    tmp_env="$(mktemp)"

    cat > "$tmp_env" <<ENV
DISCORD_TOKEN=$token
OWNER_IDS=$owners
GUILD_ID=$guild
MAX_VPS=$max_vps
DEFAULT_RAM_MB=$ram
DEFAULT_CPU_PERCENT=$cpu
DEFAULT_DISK_MB=$disk
DEFAULT_DAYS=$days
LXC_PATH=$lxc
ENV

    install -m 600 "$tmp_env" "$ENV_FILE"
    rm -f "$tmp_env"

    unset token old_token
    ok "Environment configuration saved securely."
    ok ".env.example has been preserved."
}

install_dependencies() {
    info "Updating system packages..."
    export DEBIAN_FRONTEND=noninteractive

    apt-get update -y
    apt-get install -y \
        python3 python3-venv python3-pip \
        curl ca-certificates tar sqlite3 snapd

    ok "System dependencies installed."

    if ! command -v snap >/dev/null 2>&1; then
        fail "Snap is unavailable. Check your Ubuntu installation."
        return 1
    fi

    if [[ ! -x /snap/bin/lxc ]]; then
        info "Installing LXD..."
        snap install lxd
    else
        ok "LXD is already installed."
    fi

    if ! /snap/bin/lxc info >/dev/null 2>&1; then
        info "Initializing LXD with automatic defaults..."
        lxd init --auto
    else
        ok "Existing LXD configuration detected."
    fi

    /snap/bin/lxc info >/dev/null
    ok "LXD is responding."
}

install_python() {
    cd "$INSTALL_DIR"

    info "Preparing Python environment..."
    python3 -m venv venv

    venv/bin/python -m pip install --upgrade pip
    venv/bin/python -m pip install -r requirements.txt

    mkdir -p data logs
    ok "Python dependencies installed."
}

create_service() {
    cat > "$SERVICE_FILE" <<'UNIT'
[Unit]
Description=HERO CLOUD Discord VPS Bot
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/hero-cloud
EnvironmentFile=/opt/hero-cloud/.env
ExecStart=/opt/hero-cloud/venv/bin/python -u -m bot.bot
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
UNIT

    chmod 644 "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable "$SERVICE"

    ok "Systemd service configured."
}

install_hero() {
    banner
    info "Starting HERO CLOUD installation..."

    install_dependencies
    download_project
    configure_environment
    install_python
    create_service

    echo
    ok "HERO CLOUD installation completed."
    echo
    echo "Installation directory: $INSTALL_DIR"
    echo "Configuration file: $ENV_FILE"
    echo "Service: $SERVICE"
    echo
    read -r -p "Start HERO CLOUD now? [Y/n]: " answer

    if [[ "${answer,,}" != "n" ]]; then
        systemctl restart "$SERVICE"
        sleep 2
        systemctl status "$SERVICE" --no-pager || true
    fi

    read -r -p "Press Enter to return to menu..."
}

update_hero() {
    banner
    info "Updating HERO CLOUD..."

    download_project
    install_python
    create_service

    systemctl restart "$SERVICE"
    ok "Update completed."
    read -r -p "Press Enter to return to menu..."
}

start_bot() {
    systemctl start "$SERVICE"
    ok "HERO CLOUD started."
}

stop_bot() {
    systemctl stop "$SERVICE"
    ok "HERO CLOUD stopped."
}

restart_bot() {
    systemctl restart "$SERVICE"
    ok "HERO CLOUD restarted."
}

bot_status() {
    systemctl status "$SERVICE" --no-pager || true
    read -r -p "Press Enter to return to menu..."
}

view_logs() {
    journalctl -u "$SERVICE" -n 80 --no-pager || true
    read -r -p "Press Enter to return to menu..."
}

uninstall_hero() {
    echo
    echo "This removes the HERO CLOUD application and service."
    echo "It does NOT delete LXD containers or the LXD installation."
    read -r -p "Continue? [y/N]: " answer

    [[ "${answer,,}" == "y" ]] || return

    systemctl disable --now "$SERVICE" 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload

    if [[ -d "$INSTALL_DIR" ]]; then
        read -r -p "Also remove $INSTALL_DIR and its .env? [y/N]: " remove
        if [[ "${remove,,}" == "y" ]]; then
            rm -rf "$INSTALL_DIR"
        fi
    fi

    ok "HERO CLOUD service removed."
    read -r -p "Press Enter to return to menu..."
}

main_menu() {
    require_root

    while true; do
        banner
        echo "  [1] Install HERO CLOUD"
        echo "  [2] Update HERO CLOUD"
        echo "  [3] Start Bot"
        echo "  [4] Stop Bot"
        echo "  [5] Restart Bot"
        echo "  [6] Bot Status"
        echo "  [7] View Logs"
        echo "  [8] Uninstall HERO CLOUD"
        echo "  [0] Exit"
        echo
        read -r -p "Select an option: " choice

        case "$choice" in
            1) install_hero ;;
            2) update_hero ;;
            3) start_bot ;;
            4) stop_bot ;;
            5) restart_bot ;;
            6) bot_status ;;
            7) view_logs ;;
            8) uninstall_hero ;;
            0) exit 0 ;;
            *) fail "Invalid option."; sleep 1 ;;
        esac
    done
}

main_menu
