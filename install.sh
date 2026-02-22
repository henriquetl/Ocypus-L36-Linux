#!/usr/bin/env bash
set -euo pipefail

# Defaults
UNIT="c"
SENSOR="k10temp"
RATE="1"
IFACE=""            # vazio = não força --interface
SERVICE_NAME="ocypus-l36"
INSTALL_DIR="/opt/ocypus"
SERVICE_DIR="/etc/systemd/system"

# NEW: filename in this repo
SCRIPT_IN_REPO="ocypus-L36-control.py"
SCRIPT_AT_INSTALL="${INSTALL_DIR}/ocypus-L36-control.py"

usage() {
  cat <<EOF
Usage: sudo bash install.sh [--unit c|f] [--sensor k10temp|coretemp] [--rate 1] [--interface 1] [--name ocypus-l36]

Examples:
  sudo bash install.sh
  sudo bash install.sh --interface 1
  sudo bash install.sh --sensor coretemp --unit c --rate 1 --name ocypus-l36
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unit) UNIT="$2"; shift 2 ;;
    --sensor) SENSOR="$2"; shift 2 ;;
    --rate) RATE="$2"; shift 2 ;;
    --interface) IFACE="$2"; shift 2 ;;
    --name) SERVICE_NAME="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh ..."
  exit 1
fi

if [[ ! -f "${SCRIPT_IN_REPO}" ]]; then
  echo "Error: ${SCRIPT_IN_REPO} not found in this folder."
  echo "You should run install.sh from inside the cloned repo directory."
  exit 1
fi

echo "[1/5] Installing dependencies (Arch/CachyOS)..."
if command -v pacman >/dev/null 2>&1; then
  pacman -Syu --needed --noconfirm python python-hidapi python-psutil usbutils
else
  echo "pacman not found. Install manually: python, hidapi, psutil"
  exit 1
fi

echo "[2/5] Installing script to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
install -m 755 "./${SCRIPT_IN_REPO}" "${SCRIPT_AT_INSTALL}"

echo "[3/5] Installing systemd service..."
mkdir -p "${SERVICE_DIR}"
SERVICE_PATH="${SERVICE_DIR}/${SERVICE_NAME}.service"

IFACE_ARG=""
if [[ -n "${IFACE}" ]]; then
  IFACE_ARG=" --interface ${IFACE}"
fi

EXEC="/usr/bin/python3 ${SCRIPT_AT_INSTALL} on -u ${UNIT} -s \"${SENSOR}\" -r ${RATE}${IFACE_ARG}"

cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=Ocypus L36 LCD Temperature Display
After=multi-user.target

[Service]
Type=simple
User=root
ExecStart=${EXEC}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "[4/5] Enabling service on boot..."
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

echo "[5/5] Done! Status:"
systemctl --no-pager status "${SERVICE_NAME}.service" || true

echo ""
echo "Logs:"
echo "  journalctl -u ${SERVICE_NAME}.service -f"
