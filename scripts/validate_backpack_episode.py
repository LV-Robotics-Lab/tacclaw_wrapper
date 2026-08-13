#!/usr/bin/env python3
"""Validate one downloaded Daimon Ugripper episode without modifying it."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List


def fail(message: str) -> None:
    print(f"校验失败：{message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("用法：validate_backpack_episode.py <episode目录>")

    episode_dir = Path(sys.argv[1])
    metadata_path = episode_dir / "metadata.json"
    if not metadata_path.is_file():
        fail(f"缺少 {metadata_path}")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"metadata.json 无法读取：{exc}")

    required = metadata.get("require_files")
    if not isinstance(required, list) or not required:
        fail("metadata.json 中没有有效的 require_files")

    missing: List[str] = []
    empty: List[str] = []
    total_bytes = 0
    for name in required:
        path = episode_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        size = path.stat().st_size
        total_bytes += size
        if size == 0:
            empty.append(name)

    if missing:
        fail("缺少必需文件：" + ", ".join(missing))
    if empty:
        fail("以下必需文件为空：" + ", ".join(empty))

    mode = metadata.get("device_mode", "unknown")
    quality = metadata.get("quality_check_status", "unknown")
    duration = metadata.get("collection_duration_s", "unknown")
    print("校验通过")
    print(f"  episode: {metadata.get('episode_name', episode_dir.name)}")
    print(f"  device_mode: {mode}")
    print(f"  quality_check_status: {quality}")
    print(f"  collection_duration_s: {duration}")
    print(f"  required_files: {len(required)} 个，均存在且非空")
    print(f"  required_file_bytes: {total_bytes:,}")

    if mode != "dual":
        print("  警告：该 episode 不是双爪模式", file=sys.stderr)
    if quality != "success":
        print("  警告：背包质量检查状态不是 success", file=sys.stderr)


if __name__ == "__main__":
    main()
