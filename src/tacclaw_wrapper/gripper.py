"""Safety-gated adapter around the DM gripper SDK object."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .config import GripperConfig
from .vendor import load_gripper_class


class MotionAuthorizationError(RuntimeError):
    pass


class GripperInitializationError(RuntimeError):
    pass


class GripperNotInitializedError(RuntimeError):
    pass


def _validate_speed_or_torque(value: int, name: str) -> int:
    resolved = int(value)
    if not 10 <= resolved <= 100:
        raise ValueError(f"{name} must be in 10..100")
    return resolved


def _validate_position(value: int) -> int:
    resolved = int(value)
    if not 0 <= resolved <= 1000:
        raise ValueError("position must be in 0..1000")
    return resolved


class TacClawGripper:
    """Small lifecycle wrapper; construction itself never opens hardware."""

    def __init__(self, config: GripperConfig, driver: Any):
        self.config = config
        self._driver = driver
        self._initialized = False
        self._closed = False

    @classmethod
    def connect(
        cls,
        config: GripperConfig,
        *,
        vendor_root: Path,
        driver_factory: Optional[Callable[..., Any]] = None,
    ) -> "TacClawGripper":
        factory = driver_factory or load_gripper_class(vendor_root)
        driver = factory(
            server_address=config.server_address,
            interface=config.interface,
            bitrate=config.bitrate,
        )
        return cls(config, driver)

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def closed(self) -> bool:
        return self._closed

    def initialize(
        self,
        *,
        speed: int,
        torque: int,
        clearance_confirmed: bool,
    ) -> None:
        if not clearance_confirmed:
            raise MotionAuthorizationError(
                "gripper initialization requires explicit clearance confirmation"
            )
        resolved_speed = _validate_speed_or_torque(speed, "speed")
        resolved_torque = _validate_speed_or_torque(torque, "torque")
        if not self._driver.grip_init():
            raise GripperInitializationError("vendor grip_init returned false")
        self._driver.set_torque_limit(resolved_torque)
        self._driver.set_speed(resolved_speed)
        self._initialized = True

    def move_to_position(
        self,
        position: int,
        *,
        clearance_confirmed: bool,
    ) -> Any:
        if not clearance_confirmed:
            raise MotionAuthorizationError(
                "gripper motion requires explicit clearance confirmation"
            )
        if not self._initialized:
            raise GripperNotInitializedError("initialize the gripper before motion")
        resolved_position = _validate_position(position)
        self._driver.move_to_pos(resolved_position)
        return self._driver.read_pos()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._driver.close()

    def __enter__(self) -> "TacClawGripper":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
