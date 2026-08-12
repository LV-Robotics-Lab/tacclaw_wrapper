"""Vendor SDK discovery kept behind one narrow import boundary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional, Union


def resolve_vendor_root(
    explicit: Optional[Union[str, Path]] = None,
    *,
    repo_root: Optional[Path] = None,
) -> Path:
    configured = explicit or os.environ.get("DM_VENDOR_ROOT") or "vendor/dm_tacclaw"
    root = Path(configured).expanduser()
    if not root.is_absolute():
        root = (repo_root or Path.cwd()) / root
    return root.resolve()


def vendor_python_paths(vendor_root: Path) -> Iterable[Path]:
    yield vendor_root / "gripper"
    yield vendor_root / "fish_cam"
    yield vendor_root / "SDK_Publish_V1.2.13_gripper"


def add_vendor_paths(vendor_root: Path) -> None:
    for candidate in vendor_python_paths(vendor_root):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def load_gripper_class(vendor_root: Path):
    add_vendor_paths(vendor_root)
    from gripper import Gripper

    return Gripper


def load_camera_class(vendor_root: Path):
    add_vendor_paths(vendor_root)
    from remote_camera import RemoteCameraCapture

    return RemoteCameraCapture
