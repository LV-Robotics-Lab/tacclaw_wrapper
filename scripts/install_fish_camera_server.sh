#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_root="${TACCLAW_CAMERA_INSTALL_ROOT:-/app/tacclaw-camera-server}"
venv="$install_root/venv"
service_source="$repo_root/deploy/tacclaw-camera-server.service"
service_target="/etc/systemd/system/tacclaw-camera-server.service"

if [ ! -c /dev/video4 ]; then
  echo "camera device is missing or is not a character device: /dev/video4" >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

mkdir -p "$install_root"
wheel_dir="$repo_root/vendor/offline-wheels"
grpc_wheel=("$wheel_dir"/grpcio-*-cp310-*-aarch64.whl)
if [ ! -f "${grpc_wheel[0]}" ]; then
  echo "offline ARM64 grpcio wheel is missing under $wheel_dir" >&2
  exit 1
fi

python3 -m venv --system-site-packages "$venv"
"$venv/bin/python" -m pip install --no-index --find-links "$wheel_dir" "${grpc_wheel[0]}"
PYTHONPATH="$repo_root/src" "$venv/bin/python" -c \
  'import grpc; from tacclaw_wrapper.fish_camera_proxy import camera_proxy_pb2; print("grpc", grpc.__version__)'

sudo install -m 0644 "$service_source" "$service_target"
sudo systemctl daemon-reload
sudo systemctl enable --now tacclaw-camera-server.service
sudo systemctl --no-pager --full status tacclaw-camera-server.service
