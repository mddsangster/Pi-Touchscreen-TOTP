#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run as root. Use sudo ./install_python_packages.sh"
  exit 1
fi

wait_for_apt_locks() {
  local waited=0
  local timeout=300

  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 \
    || fuser /var/lib/dpkg/lock >/dev/null 2>&1 \
    || fuser /var/lib/apt/lists/lock >/dev/null 2>&1 \
    || fuser /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if [ "$waited" -ge "$timeout" ]; then
      echo "Timed out waiting for apt/dpkg lock after ${timeout}s."
      return 1
    fi
    echo "apt/dpkg is busy (likely packagekit/unattended upgrades); waiting... (${waited}s/${timeout}s)"
    sleep 5
    waited=$((waited + 5))
  done
}

wait_for_apt_locks

echo "Updating apt package lists..."
apt-get update

wait_for_apt_locks

echo "Installing required Python packages..."
apt-get install -y python3-onetimepass python3-pygame

echo "Installation complete."
