#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root. Use sudo ./install_autopull.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="otp-autopull.service"
TIMER_NAME="otp-autopull.timer"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
TIMER_PATH="/etc/systemd/system/${TIMER_NAME}"
AUTOPULL_SCRIPT="$PROJECT_DIR/pull_latest.sh"
SYNC_USER="${SUDO_USER:-starscream}"
BRANCH="${1:-main}"
REMOTE="${2:-origin}"
INTERVAL="${3:-1min}"

if [ ! -f "$AUTOPULL_SCRIPT" ]; then
  echo "Missing script: $AUTOPULL_SCRIPT"
  exit 1
fi

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=OTP Git auto-pull service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
ExecStart=/bin/bash $AUTOPULL_SCRIPT $BRANCH $REMOTE $SYNC_USER
StandardOutput=journal
StandardError=journal
EOF

cat > "$TIMER_PATH" <<EOF
[Unit]
Description=Run OTP Git auto-pull periodically

[Timer]
OnBootSec=45s
OnUnitActiveSec=$INTERVAL
AccuracySec=15s
Persistent=true
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
EOF

chmod 644 "$SERVICE_PATH" "$TIMER_PATH"
systemctl daemon-reload
systemctl enable --now "$TIMER_NAME"

echo "Installed $SERVICE_NAME and $TIMER_NAME"
echo "Sync user: $SYNC_USER"
echo "Branch/remote: $BRANCH on $REMOTE"
echo "Interval: $INTERVAL"
echo "Check status: systemctl status $TIMER_NAME"
echo "Run now: systemctl start $SERVICE_NAME"
