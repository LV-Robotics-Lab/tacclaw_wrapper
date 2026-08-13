#!/usr/bin/env bash
set -euo pipefail

BACKPACK_IP="${BACKPACK_IP:-192.168.2.240}"
BACKPACK_USER="${BACKPACK_USER:-root}"
DEST_ROOT="${BACKPACK_DATA_DIR:-$(pwd)/backpack_data}"
ACTION="${1:-help}"
SELECTION="${2:-latest}"

CONTROL_SOCKET="/tmp/tacclaw-backpack-ssh-${UID}-$$"
SSH_OPTIONS=(
  -o "ControlMaster=auto"
  -o "ControlPath=${CONTROL_SOCKET}"
  -o "ControlPersist=60"
  -o "ConnectTimeout=8"
  -o "StrictHostKeyChecking=accept-new"
)
TARGET="${BACKPACK_USER}@${BACKPACK_IP}"

usage() {
  cat <<'EOF'
通过网线读取 Daimon 双爪采集背包（只读，不删除背包数据）。

用法：
  ./scripts/backpack_data.sh status
  ./scripts/backpack_data.sh list
  ./scripts/backpack_data.sh pull latest [本地目录]
  ./scripts/backpack_data.sh pull episode_YYYYMMDD_NNNN [本地目录]

环境变量：
  BACKPACK_IP        背包地址，默认 192.168.2.240
  BACKPACK_USER      SSH 用户，默认 root
  BACKPACK_DATA_DIR  默认下载根目录，默认 ./backpack_data

脚本会提示输入背包 SSH 密码，但不会保存密码。
EOF
}

cleanup() {
  ssh -S "${CONTROL_SOCKET}" -O exit "${TARGET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

case "${ACTION}" in
  status|list|pull) ;;
  help|-h|--help)
    usage
    exit 0
    ;;
  *)
    echo "未知操作：${ACTION}" >&2
    usage >&2
    exit 2
    ;;
esac

if ! ip route get "${BACKPACK_IP}" >/dev/null 2>&1; then
  echo "无法找到通往背包 ${BACKPACK_IP} 的路由。" >&2
  echo "请先启用 NetworkManager 连接：nmcli connection up TacClaw-backpack" >&2
  exit 1
fi

if ! ping -c 1 -W 2 "${BACKPACK_IP}" >/dev/null 2>&1; then
  echo "背包 ${BACKPACK_IP} 没有响应。请检查背包电源、网线和 TacClaw-backpack 网络连接。" >&2
  exit 1
fi

# 建立一个短时复用的 SSH 连接，后续 list/rsync 不会反复询问密码。
ssh "${SSH_OPTIONS[@]}" "${TARGET}" true

REMOTE_DATA_ROOT="$(
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "find /mnt/data_disk -mindepth 2 -maxdepth 2 -type d -name data -print -quit"
)"

if [[ -z "${REMOTE_DATA_ROOT}" ]]; then
  echo "背包数据盘未挂载，或没有找到 /mnt/data_disk/<device_sn>/data。" >&2
  exit 1
fi

if [[ "${ACTION}" == "status" ]]; then
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "printf 'hostname: '; hostname; \
     printf 'time: '; date '+%F %T %Z'; \
     printf 'data_root: '; printf '%s\\n' '${REMOTE_DATA_ROOT}'; \
     df -hT /mnt/data_disk | tail -n 1; \
     systemctl is-active ugripper.service databot-device-joint.service"
  exit 0
fi

if [[ "${ACTION}" == "list" ]]; then
  echo "背包中的已完成 episode："
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "find '${REMOTE_DATA_ROOT}' -mindepth 2 -maxdepth 2 -type f -name metadata.json -printf '%TY-%Tm-%Td %TH:%TM:%TS %h\\n' | sort"
  exit 0
fi

if [[ "${SELECTION}" == "latest" ]]; then
  REMOTE_EPISODE_DIR="$(
    ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
      "find '${REMOTE_DATA_ROOT}' -mindepth 2 -maxdepth 2 -type f -name metadata.json -printf '%T@ %h\\n' | sort -n | tail -n 1 | cut -d' ' -f2-"
  )"
  if [[ -z "${REMOTE_EPISODE_DIR}" ]]; then
    echo "背包中没有已完成的 episode。" >&2
    exit 1
  fi
  EPISODE="${REMOTE_EPISODE_DIR##*/}"
else
  if [[ ! "${SELECTION}" =~ ^episode_[0-9]{8}_[0-9]{4}$ ]]; then
    echo "episode 名称格式无效：${SELECTION}" >&2
    exit 2
  fi
  EPISODE="${SELECTION}"
  REMOTE_EPISODE_DIR="${REMOTE_DATA_ROOT}/${EPISODE}"
  if ! ssh "${SSH_OPTIONS[@]}" "${TARGET}" test -f "${REMOTE_EPISODE_DIR}/metadata.json"; then
    echo "找不到已完成的 episode：${EPISODE}" >&2
    exit 1
  fi
fi

if [[ $# -ge 3 ]]; then
  DEST_ROOT="$3"
fi
mkdir -p "${DEST_ROOT}/${EPISODE}"

echo "正在下载 ${EPISODE} 到 ${DEST_ROOT}/${EPISODE}/"
rsync \
  --archive \
  --partial \
  --human-readable \
  --info=progress2 \
  -e "ssh -o ControlPath=${CONTROL_SOCKET}" \
  "${TARGET}:${REMOTE_EPISODE_DIR}/" \
  "${DEST_ROOT}/${EPISODE}/"

python3 "$(dirname "$0")/validate_backpack_episode.py" "${DEST_ROOT}/${EPISODE}"
