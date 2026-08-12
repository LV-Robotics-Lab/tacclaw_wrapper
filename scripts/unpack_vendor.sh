#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_dir="${DM_VENDOR_SOURCE_DIR:-$repo_root/vendor/source}"
dest="${DM_VENDOR_EXTRACT_DIR:-$repo_root/vendor/dm_tacclaw}"

if [ ! -d "$src_dir" ]; then
  echo "DM vendor source directory not found: $src_dir" >&2
  echo "Copy the three vendor zip files there or set DM_VENDOR_SOURCE_DIR." >&2
  exit 1
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required." >&2
  exit 1
fi

mkdir -p "$dest"

for zip_name in gripper.zip fish_cam.zip SDK_Publish_V1.2.13_gripper.zip; do
  zip_path="$src_dir/$zip_name"
  if [ ! -f "$zip_path" ]; then
    echo "missing: $zip_path" >&2
    continue
  fi
  echo "[unpack] $zip_path -> $dest"
  unzip -n "$zip_path" -d "$dest"
done

echo "[unpack] done: $dest"
