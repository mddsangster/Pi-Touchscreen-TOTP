#!/bin/bash
set -euo pipefail

BRANCH="${1:-main}"
REMOTE="${2:-origin}"
GIT_USER="${3:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="${OTP_SERVICE_NAME:-otp-codes.service}"

cd "$PROJECT_DIR"

if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "Not a git repository: $PROJECT_DIR"
  exit 1
fi

ensure_git_permissions() {
  if [ -z "$GIT_USER" ] || [ "$(id -u)" -ne 0 ]; then
    return 0
  fi

  local git_dir="$PROJECT_DIR/.git"
  local objects_dir="$git_dir/objects"
  local git_dir_quoted
  local objects_dir_quoted

  if [ ! -d "$objects_dir" ]; then
    return 0
  fi

  printf -v git_dir_quoted '%q' "$git_dir"
  printf -v objects_dir_quoted '%q' "$objects_dir"

  if runuser -l "$GIT_USER" -c "test -w $git_dir_quoted && test -w $objects_dir_quoted"; then
    return 0
  fi

  echo "[autopull] Repairing git ownership in $git_dir for user $GIT_USER"
  chown -R "$GIT_USER:$GIT_USER" "$git_dir"
}

git_cmd() {
  if [ -n "$GIT_USER" ] && [ "$(id -u)" -eq 0 ]; then
    local git_command
    local project_dir_quoted
    printf -v git_command '%q ' git "$@"
    printf -v project_dir_quoted '%q' "$PROJECT_DIR"
    runuser -l "$GIT_USER" -c "cd $project_dir_quoted && ${git_command% }"
  else
    git "$@"
  fi
}

echo "[autopull] Fetching $REMOTE/$BRANCH"
ensure_git_permissions
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
