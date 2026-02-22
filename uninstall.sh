#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${1:-ocypus-l36}"
INSTALL_DIR="/opt/ocypus"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
  echo "Run: sudo bash uninstall.sh [service-name]"
  exit 1
fi

systemctl disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
rm -f "${SERVICE_PATH}"
systemctl daemon-reload
rm -rf "${INSTALL_DIR}"

echo "Removed: ${SERVICE_NAME}.service and ${INSTALL_DIR}"
