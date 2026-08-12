"""Read-only wrapper around the DM TacClaw fisheye camera client."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .vendor import load_camera_class


class CameraReadError(RuntimeError):
    """Raised when the vendor camera client cannot return a frame."""


@dataclass(frozen=True)
class CameraConfig:
    side: str
    host: str
    port: int = 50088
    codec: str = "MJPG"
    width: int = 1920
    height: int = 1080
    fps: int = 60
    client_ip: str = ""

    def __post_init__(self) -> None:
        if self.side not in {"left", "right"}:
            raise ValueError("side must be 'left' or 'right'")
        if not self.host.strip():
            raise ValueError("host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be in 1..65535")
        if self.codec not in {"MJPG", "HEVC"}:
            raise ValueError("codec must be MJPG or HEVC")
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("width, height, and fps must be positive")

    @classmethod
    def from_env(
        cls,
        side: str,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        codec: str = "MJPG",
        width: int = 1920,
        height: int = 1080,
        fps: int = 60,
        client_ip: str = "",
        environ: Optional[Mapping[str, str]] = None,
    ) -> "CameraConfig":
        values = os.environ if environ is None else environ
        host_key = "DM_LEFT_HOST" if side == "left" else "DM_RIGHT_HOST"
        fallback = "192.168.127.10" if side == "left" else "192.168.127.11"
        return cls(
            side=side,
            host=host or values.get(host_key, fallback),
            port=(
                int(values.get("DM_FISH_CAMERA_GRPC_PORT", "50088"))
                if port is None
                else port
            ),
            codec=codec,
            width=width,
            height=height,
            fps=fps,
            client_ip=client_ip,
        )


class TacClawCamera:
    """A read-only camera lifecycle; no method can command the gripper."""

    def __init__(self, config: CameraConfig, capture: Any):
        self.config = config
        self._capture = capture
        self._opened = False
        self._closed = False

    @classmethod
    def capabilities(
        cls,
        config: CameraConfig,
        *,
        vendor_root: Path,
        driver_factory: Optional[Callable[..., Any]] = None,
    ) -> Any:
        factory = driver_factory or load_camera_class(vendor_root)
        return factory.list_capabilities(config.host, port=config.port)

    @classmethod
    def connect(
        cls,
        config: CameraConfig,
        *,
        vendor_root: Path,
        driver_factory: Optional[Callable[..., Any]] = None,
    ) -> "TacClawCamera":
        factory = driver_factory or load_camera_class(vendor_root)
        capture = factory(
            host=config.host,
            port=config.port,
            codec=config.codec,
            width=config.width,
            height=config.height,
            fps=config.fps,
            client_ip=config.client_ip,
        )
        return cls(config, capture)

    def open(self) -> None:
        self._capture.open()
        self._opened = True

    def read_once(self, *, timeout: float = 2.0) -> Any:
        if not self._opened:
            raise CameraReadError("open the camera before reading")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        ok, frame = self._capture.read(timeout=timeout)
        if not ok:
            detail = self._capture.get("error")
            raise CameraReadError(f"camera read failed: {detail}")
        return frame

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._capture.release()

    def __enter__(self) -> "TacClawCamera":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
