#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
remote_user="${TACCLAW_CAMERA_SSH_USER:-cftc}"
remote_root="/app/tacclaw-camera-server/source"

if [ "$#" -eq 0 ]; then
  boards=(192.168.127.10 192.168.127.11)
else
  boards=("$@")
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required" >&2
  exit 1
fi

for board in "${boards[@]}"; do
  target="$remote_user@$board"
  echo "[deploy] preparing $target"
  ssh -t "$target" \
    "sudo install -d -o '$remote_user' -g '$remote_user' /app/tacclaw-camera-server '$remote_root'"
  rsync -az --delete \
    --exclude '.git/' \
    --exclude '.pytest_cache/' \
    --exclude '__pycache__/' \
    --exclude 'vendor/dm_tacclaw/' \
    --exclude 'vendor/source/' \
    "$repo_root/" "$target:$remote_root/"
  ssh -t "$target" "bash '$remote_root/scripts/install_fish_camera_server.sh'"
done

echo "[deploy] both camera proxies are installed"
