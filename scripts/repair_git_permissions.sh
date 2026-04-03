#!/bin/bash
# Repairs root-owned .git files that prevent non-root git operations.
# Run once with: sudo bash scripts/repair_git_permissions.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

# Detect repo owner from the project directory itself
REPO_USER="$(stat -c '%U' "$PROJECT_DIR")"

echo "Repairing .git ownership -> $REPO_USER in $PROJECT_DIR"
chown -R "$REPO_USER:$REPO_USER" "$PROJECT_DIR/.git"
echo "Done. You can now run: git pull"
