"""Vendor SDK discovery kept behind one narrow import boundary.

DM has shipped two Python client layouts for the gripper.  The current product
manual documents ``dm_lingkong_grip_sdk.LingkongGrip`` and a constructor that
accepts only ``server_address``.  The older archived client exposes
``gripper.Gripper`` and additionally accepts the remote CAN interface and
bitrate.  Keep that difference here so integration callers never need to
import, identify, or special-case a vendor module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable, Optional, Union


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
    yield vendor_root
    yield vendor_root / "gripper"
    yield vendor_root / "fish_cam"
    yield vendor_root / "SDK_Publish_V1.2.13_gripper"


def add_vendor_paths(vendor_root: Path) -> None:
    for candidate in vendor_python_paths(vendor_root):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def _load_gripper_backend(vendor_root: Path) -> tuple[Any, str]:
    add_vendor_paths(vendor_root)

    try:
        from dm_lingkong_grip_sdk import LingkongGrip
    except ModuleNotFoundError as exc:
        # A missing dependency inside an installed official SDK is a real SDK
        # error.  Falling back in that case would hide a broken installation.
        if exc.name != "dm_lingkong_grip_sdk":
            raise
    else:
        return LingkongGrip, "lingkong"

    try:
        from gripper import Gripper
    except ModuleNotFoundError as exc:
        if exc.name != "gripper":
            raise
        raise ModuleNotFoundError(
            "no supported DM TacClaw gripper SDK was found; expected "
            "dm_lingkong_grip_sdk.LingkongGrip (current manual) or "
            "gripper.Gripper (legacy archive)"
        ) from exc

    return Gripper, "legacy_remote_can"


def load_gripper_class(vendor_root: Path):
    """Return the preferred installed vendor class without opening hardware."""

    gripper_class, _backend = _load_gripper_backend(vendor_root)
    return gripper_class


def create_gripper_driver(
    vendor_root: Path,
    *,
    server_address: str,
    interface: str,
    bitrate: int,
):
    """Construct the installed vendor client using its documented signature."""

    gripper_class, backend = _load_gripper_backend(vendor_root)
    if backend == "lingkong":
        return gripper_class(server_address=server_address)

    return gripper_class(
        server_address=server_address,
        interface=interface,
        bitrate=bitrate,
    )


def load_camera_class(vendor_root: Path):
    add_vendor_paths(vendor_root)
    from remote_camera import RemoteCameraCapture

    return RemoteCameraCapture
