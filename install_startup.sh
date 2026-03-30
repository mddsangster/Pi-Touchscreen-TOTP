#!/bin/bash
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root. Use sudo ./install_startup.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="otp-codes.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
PYTHON_INSTALL_SCRIPT="$PROJECT_DIR/scripts/install_python_packages.sh"
SERVICE_USER="${SUDO_USER:-root}"

if [ -f "$PYTHON_INSTALL_SCRIPT" ]; then
  echo "Installing required Python packages (will wait if apt/dpkg is locked)..."
  bash "$PYTHON_INSTALL_SCRIPT"
else
  echo "Warning: $PYTHON_INSTALL_SCRIPT not found. Skipping package install."
fi

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=One-Time Password display service
After=network-online.target systemd-udev-settle.service
Wants=network-online.target systemd-udev-settle.service

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStartPre=/bin/sh -c 'i=0; while [ "\$i" -lt 40 ]; do if [ -e /dev/dri/card0 ] || [ -e /dev/fb0 ]; then exit 0; fi; i=\$((i + 1)); sleep 1; done; echo "Display device not ready" >&2; exit 1'
ExecStart=/usr/bin/python3 -u $PROJECT_DIR/generate_codes.py --watch --pygame
Restart=always
RestartSec=3
TimeoutStartSec=90
User=$SERVICE_USER
Group=video
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONFAULTHANDLER=1
Environment=SDL_AUDIODRIVER=dummy
StandardInput=null
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_PATH"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "Service installed: $SERVICE_NAME"
echo "Service user: $SERVICE_USER"
echo "Use 'systemctl start $SERVICE_NAME' to start it now, or reboot to run on boot."
