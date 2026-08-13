#!/usr/bin/env bash
set -euo pipefail

BACKPACK_IP="${BACKPACK_IP:-192.168.2.240}"
BACKPACK_USER="${BACKPACK_USER:-root}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="${SCRIPT_DIR}/validate_backpack_episode.py"

DRY_RUN=false
KEEP_REMOTE=false
ASSUME_YES=false
LATEST_ONLY=false
DEST_ROOT=""

usage() {
  cat <<'EOF'
自动导出 Daimon 背包中已完成的 episode，并在完整校验后删除背包原件。

用法：
  ./scripts/export_backpack_data.sh <目标文件夹> [选项]

选项：
  --latest        只处理最新一条；默认处理全部已完成 episode
  --keep-remote   只下载和校验，不删除背包原件
  --dry-run       只显示将要处理的数据，不下载或删除
  --yes           不询问 DELETE 确认（适合自动化，使用时务必谨慎）
  -h, --help      显示帮助

示例：
  ./scripts/export_backpack_data.sh /media/feibo/SANDISK\ ELE/TacClaw
  ./scripts/export_backpack_data.sh ./exported_data --latest
  ./scripts/export_backpack_data.sh ./exported_data --keep-remote

安全规则：
  - 只处理包含 metadata.json 的 episode_YYYYMMDD_NNNN 目录。
  - 忽略正在录制或封装的 episode_*-temp。
  - 下载后校验 metadata.json 的必需文件，并逐文件核对 SHA-256。
  - 仅当全部校验通过后，才删除对应的背包 episode。
EOF
}

while (($#)); do
  case "$1" in
    --latest) LATEST_ONLY=true ;;
    --keep-remote) KEEP_REMOTE=true ;;
    --dry-run) DRY_RUN=true ;;
    --yes) ASSUME_YES=true ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "未知选项：$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "${DEST_ROOT}" ]]; then
        echo "只能指定一个目标文件夹。" >&2
        exit 2
      fi
      DEST_ROOT="$1"
      ;;
  esac
  shift
done

if [[ -z "${DEST_ROOT}" ]]; then
  echo "缺少目标文件夹。" >&2
  usage >&2
  exit 2
fi

if [[ ! -x "${VALIDATOR}" ]]; then
  echo "找不到校验程序：${VALIDATOR}" >&2
  exit 1
fi

CONTROL_SOCKET="/tmp/tacclaw-export-ssh-${UID}-$$"
SSH_OPTIONS=(
  -o "ControlMaster=auto"
  -o "ControlPath=${CONTROL_SOCKET}"
  -o "ControlPersist=60"
  -o "ConnectTimeout=8"
  -o "StrictHostKeyChecking=accept-new"
)
TARGET="${BACKPACK_USER}@${BACKPACK_IP}"

cleanup() {
  ssh -S "${CONTROL_SOCKET}" -O exit "${TARGET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! ping -c 1 -W 2 "${BACKPACK_IP}" >/dev/null 2>&1; then
  echo "背包 ${BACKPACK_IP} 没有响应，请检查电源、网线和 TacClaw-backpack 网络连接。" >&2
  exit 1
fi

# 后续命令复用该连接，只会询问一次 SSH 密码。
echo "即将连接背包 ${TARGET}。请输入背包 root 密码，不是电脑 feibo/sudo 密码。"
echo "密码输入时终端不会显示字符或星号，输入完成后直接按 Enter。"
ssh "${SSH_OPTIONS[@]}" "${TARGET}" true

REMOTE_DATA_ROOT="$(
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "find /mnt/data_disk -mindepth 2 -maxdepth 2 -type d -name data -print -quit"
)"

if [[ ! "${REMOTE_DATA_ROOT}" =~ ^/mnt/data_disk/[A-Za-z0-9_-]+/data$ ]]; then
  echo "拒绝处理不符合安全规则的数据根目录：${REMOTE_DATA_ROOT:-<空>}" >&2
  exit 1
fi

REMOTE_STATE="$(
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "sed -n 's/.*\"service_state\": \"\([^\"]*\)\".*/\1/p' /tmp/umi_stereo_camera_status.json 2>/dev/null | head -1"
)"
if [[ "${REMOTE_STATE}" != "ready" ]]; then
  echo "背包当前不是 Ready（状态：${REMOTE_STATE:-未知}），拒绝导出或删除。" >&2
  echo "请先停止采集并等待 Writing 完成。" >&2
  exit 1
fi

mapfile -t EPISODES < <(
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "find '${REMOTE_DATA_ROOT}' -mindepth 2 -maxdepth 2 -type f -name metadata.json -printf '%T@ %h\\n' | sort -n | sed 's/^[^ ]* //'"
)

if ((${#EPISODES[@]} == 0)); then
  echo "背包中没有已完成、可导出的 episode。"
  exit 0
fi

if [[ "${LATEST_ONLY}" == true ]]; then
  EPISODES=("${EPISODES[-1]}")
fi

TOTAL_BYTES=0
echo "将处理以下已完成数据："
for remote_dir in "${EPISODES[@]}"; do
  episode="${remote_dir##*/}"
  if [[ ! "${episode}" =~ ^episode_[0-9]{8}_[0-9]{4}$ ]] ||
     [[ "${remote_dir}" != "${REMOTE_DATA_ROOT}/${episode}" ]]; then
    echo "发现不安全的 episode 路径，已中止：${remote_dir}" >&2
    exit 1
  fi
  bytes="$(ssh "${SSH_OPTIONS[@]}" "${TARGET}" "find '${remote_dir}' -maxdepth 1 -type f -printf '%s\\n' | awk '{s+=\$1} END {print s+0}'")"
  TOTAL_BYTES=$((TOTAL_BYTES + bytes))
  printf '  %-28s %10s bytes\n' "${episode}" "${bytes}"
done
printf '合计：%s 条，%s bytes\n' "${#EPISODES[@]}" "${TOTAL_BYTES}"
printf '目标文件夹：%s\n' "${DEST_ROOT}"

if [[ "${DRY_RUN}" == true ]]; then
  echo "dry-run 完成：未下载，也未删除。"
  exit 0
fi

mkdir -p "${DEST_ROOT}"
DEST_ROOT="$(cd -- "${DEST_ROOT}" && pwd)"
AVAILABLE_BYTES="$(df -PB1 "${DEST_ROOT}" | awk 'NR==2 {print $4}')"
if ((AVAILABLE_BYTES < TOTAL_BYTES)); then
  echo "目标磁盘空间不足：需要至少 ${TOTAL_BYTES} bytes，当前可用 ${AVAILABLE_BYTES} bytes。" >&2
  exit 1
fi

if [[ "${KEEP_REMOTE}" == false && "${ASSUME_YES}" == false ]]; then
  echo
  echo "警告：每条数据校验成功后，会永久删除背包中的对应原件。"
  read -r -p "请输入 DELETE 继续：" confirmation
  if [[ "${confirmation}" != "DELETE" ]]; then
    echo "已取消，背包数据未改变。"
    exit 0
  fi
fi

exported=0
deleted=0
for remote_dir in "${EPISODES[@]}"; do
  episode="${remote_dir##*/}"
  local_dir="${DEST_ROOT}/${episode}"
  mkdir -p "${local_dir}"

  echo
  echo "[${episode}] 下载中……"
  rsync \
    --archive \
    --partial \
    --human-readable \
    --info=progress2 \
    -e "ssh -o ControlPath=${CONTROL_SOCKET}" \
    "${TARGET}:${remote_dir}/" \
    "${local_dir}/"

  echo "[${episode}] 检查必需文件……"
  python3 "${VALIDATOR}" "${local_dir}"

  manifest="${local_dir}/.backpack-sha256"
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "cd '${remote_dir}' && find . -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum" \
    > "${manifest}"
  echo "[${episode}] 核对背包与本机 SHA-256……"
  (cd "${local_dir}" && sha256sum --quiet -c .backpack-sha256)
  echo "[${episode}] 下载和校验完成：${local_dir}"
  exported=$((exported + 1))

  if [[ "${KEEP_REMOTE}" == true ]]; then
    echo "[${episode}] --keep-remote：保留背包原件。"
    continue
  fi

  # 删除前再次确认：服务 Ready、没有临时 episode、目标仍为带 metadata 的精确目录。
  echo "[${episode}] 校验通过，正在删除背包原件……"
  ssh "${SSH_OPTIONS[@]}" "${TARGET}" \
    "set -eu; \
     state=\$(sed -n 's/.*\"service_state\": \"\([^\"]*\)\".*/\1/p' /tmp/umi_stereo_camera_status.json 2>/dev/null | head -1); \
     [ \"\$state\" = ready ]; \
     ! find '${REMOTE_DATA_ROOT}' -mindepth 1 -maxdepth 1 -type d -name 'episode_*-temp' -print -quit | grep -q .; \
     [ -f '${remote_dir}/metadata.json' ]; \
     [ \"${remote_dir}\" = \"${REMOTE_DATA_ROOT}/${episode}\" ]; \
     case '${episode}' in episode_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9]) ;; *) exit 2 ;; esac; \
     find '${remote_dir}' -mindepth 1 -delete; \
     rmdir '${remote_dir}'"

  if ssh "${SSH_OPTIONS[@]}" "${TARGET}" test -e "${remote_dir}"; then
    echo "[${episode}] 背包目录仍存在，删除未完成。" >&2
    exit 1
  fi
  echo "[${episode}] 背包原件已删除。"
  deleted=$((deleted + 1))
done

echo
echo "完成：成功导出 ${exported} 条；从背包删除 ${deleted} 条。"
echo "数据位置：${DEST_ROOT}"
