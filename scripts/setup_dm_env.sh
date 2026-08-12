#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$repo_root/config/dm_tacclaw.env" ]; then
  # shellcheck disable=SC1090
  . "$repo_root/config/dm_tacclaw.env"
fi

vendor_root="${DM_VENDOR_ROOT:-$repo_root/vendor/dm_tacclaw}"
case "$vendor_root" in
  /*) ;;
  *) vendor_root="$repo_root/$vendor_root" ;;
esac

python_bin="${DM_PYTHON_BIN:-python3.10}"
venv="${DM_VENV:-$repo_root/.venv-dm-tacclaw}"

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "$python_bin is required for DM TacClaw SDK compatibility." >&2
  exit 1
fi

"$python_bin" -m venv "$venv"
"$venv/bin/python" -m pip install --upgrade pip
"$venv/bin/python" -m pip install -e "$repo_root"

if [ -d "$vendor_root/gripper" ]; then
  "$venv/bin/python" -m pip install "$vendor_root/gripper"
else
  echo "warning: $vendor_root/gripper missing; run unpack_vendor.sh first" >&2
fi

if [ -f "$vendor_root/fish_cam/requirements.txt" ]; then
  "$venv/bin/python" -m pip install -r "$vendor_root/fish_cam/requirements.txt"
else
  echo "warning: fish_cam requirements missing; run unpack_vendor.sh first" >&2
fi

if [ "${INSTALL_DMROBOTICS:-0}" = "1" ]; then
  if [ -d "$vendor_root/SDK_Publish_V1.2.13_gripper" ]; then
    "$venv/bin/python" -m pip install "$vendor_root/SDK_Publish_V1.2.13_gripper"
  else
    echo "warning: tactile SDK directory missing; run unpack_vendor.sh first" >&2
  fi
else
  echo "Skipped dmrobotics tactile SDK install. Set INSTALL_DMROBOTICS=1 to install it."
fi

echo "[dm-env] python=$venv/bin/python"
