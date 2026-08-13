from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

VALIDATOR = Path(__file__).parents[1] / "scripts" / "validate_backpack_episode.py"


def run_validator(episode_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(episode_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def write_metadata(episode_dir: Path, required_files: list[str]) -> None:
    metadata = {
        "episode_name": episode_dir.name,
        "device_mode": "dual",
        "quality_check_status": "success",
        "collection_duration_s": 1.5,
        "require_files": required_files,
    }
    (episode_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_accepts_complete_episode(tmp_path: Path) -> None:
    episode_dir = tmp_path / "episode_20260813_0001"
    episode_dir.mkdir()
    write_metadata(episode_dir, ["metadata.json", "cam_left.mkv"])
    (episode_dir / "cam_left.mkv").write_bytes(b"video")

    result = run_validator(episode_dir)

    assert result.returncode == 0
    assert "校验通过" in result.stdout
    assert "required_files: 2 个" in result.stdout


def test_rejects_missing_required_file(tmp_path: Path) -> None:
    episode_dir = tmp_path / "episode_20260813_0002"
    episode_dir.mkdir()
    write_metadata(episode_dir, ["metadata.json", "sensor_left.mcap"])

    result = run_validator(episode_dir)

    assert result.returncode == 1
    assert "缺少必需文件：sensor_left.mcap" in result.stderr


def test_rejects_empty_required_file(tmp_path: Path) -> None:
    episode_dir = tmp_path / "episode_20260813_0003"
    episode_dir.mkdir()
    write_metadata(episode_dir, ["metadata.json", "cam_right.mkv"])
    (episode_dir / "cam_right.mkv").touch()

    result = run_validator(episode_dir)

    assert result.returncode == 1
    assert "以下必需文件为空：cam_right.mkv" in result.stderr
