"""Validated DM TacClaw endpoint configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class GripperConfig:
    side: str
    host: str
    port: int = 55551
    interface: str = "can0"
    bitrate: int = 1_000_000

    def __post_init__(self) -> None:
        if self.side not in {"left", "right"}:
            raise ValueError("side must be 'left' or 'right'")
        if not self.host.strip():
            raise ValueError("host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be in 1..65535")
        if not self.interface.strip():
            raise ValueError("interface must not be empty")
        if self.bitrate <= 0:
            raise ValueError("bitrate must be positive")

    @property
    def server_address(self) -> str:
        return f"{self.host}:{self.port}"

    @classmethod
    def from_env(
        cls,
        side: str,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        interface: str = "can0",
        bitrate: int = 1_000_000,
        environ: Optional[Mapping[str, str]] = None,
    ) -> "GripperConfig":
        values = os.environ if environ is None else environ
        host_key = "DM_LEFT_HOST" if side == "left" else "DM_RIGHT_HOST"
        example_host = "192.168.127.10" if side == "left" else "192.168.127.11"
        resolved_host = host or values.get(host_key, example_host)
        resolved_port = (
            int(values.get("DM_GRIPPER_GRPC_PORT", "55551"))
            if port is None
            else port
        )
        return cls(
            side=side,
            host=resolved_host,
            port=resolved_port,
            interface=interface,
            bitrate=bitrate,
        )
