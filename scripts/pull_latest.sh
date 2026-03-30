#!/bin/bash
set -euo pipefail

BRANCH="${1:-main}"
REMOTE="${2:-origin}"
GIT_USER="${3:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="${OTP_SERVICE_NAME:-otp-codes.service}"

cd "$PROJECT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repository: $PROJECT_DIR"
  exit 1
fi

git_cmd() {
  if [ -n "$GIT_USER" ] && [ "$(id -u)" -eq 0 ]; then
    runuser -u "$GIT_USER" -- git "$@"
  else
    git "$@"
  fi
}

echo "[autopull] Fetching $REMOTE/$BRANCH"
git_cmd fetch "$REMOTE" "$BRANCH"

LOCAL_SHA="$(git_cmd rev-parse HEAD)"
REMOTE_SHA="$(git_cmd rev-parse "$REMOTE/$BRANCH")"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "[autopull] Already up to date ($LOCAL_SHA)"
  exit 0
fi

if ! git_cmd diff --quiet || ! git_cmd diff --cached --quiet; then
  echo "[autopull] Local uncommitted changes detected. Skipping pull to avoid clobbering."
  exit 0
fi

echo "[autopull] Pulling updates"
git_cmd pull --rebase "$REMOTE" "$BRANCH"

NEW_SHA="$(git_cmd rev-parse HEAD)"
if [ "$NEW_SHA" != "$LOCAL_SHA" ]; then
  echo "[autopull] Updated $LOCAL_SHA -> $NEW_SHA"
  echo "[autopull] Restarting $SERVICE_NAME"
  systemctl try-restart "$SERVICE_NAME" || true
fi
