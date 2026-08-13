from __future__ import annotations

import importlib
import math
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable


class DmTacClawError(RuntimeError):
    """Raised when the DM-TacClaw cannot be operated safely."""


class DmTacClawInterface:
    """Non-blocking wrapper around the DM remote-CAN gripper SDK.

    The vendor SDK performs network I/O in its constructor and physical homing
    in ``grip_init``. Both are therefore delayed until the explicitly guarded
    execute-mode initialization call.
    """

    OPEN_POSITION = 1000
    CLOSED_POSITION = 0

    def __init__(
        self,
        *,
        arm_name: str,
        server_address: str = "192.168.127.10:55551",
        remote_can_interface: str = "can0",
        bitrate: int = 1_000_000,
        speed: int = 30,
        torque_limit: int = 30,
        command_rate_hz: float = 20.0,
        position_deadband: int = 5,
        sdk_root: str | Path | None = None,
        execute: bool = False,
        sdk_factory: Callable[..., Any] | None = None,
    ) -> None:
        if arm_name not in {"arm_a", "arm_b"}:
            raise ValueError("arm_name must be arm_a or arm_b")
        if not server_address or ":" not in server_address:
            raise ValueError("server_address must be in host:port form")
        if not remote_can_interface:
            raise ValueError("remote_can_interface must not be empty")
        if bitrate <= 0:
            raise ValueError("bitrate must be positive")
        if not 10 <= speed <= 100:
            raise ValueError("speed must be within [10, 100]")
        if not 10 <= torque_limit <= 100:
            raise ValueError("torque_limit must be within [10, 100]")
        if command_rate_hz <= 0.0:
            raise ValueError("command_rate_hz must be positive")
        if not 0 <= position_deadband <= 1000:
            raise ValueError("position_deadband must be within [0, 1000]")

        self.arm_name = arm_name
        self.server_address = server_address
        self.remote_can_interface = remote_can_interface
        self.bitrate = bitrate
        self.speed = speed
        self.torque_limit = torque_limit
        self.command_rate_hz = command_rate_hz
        self.position_deadband = position_deadband
        self.sdk_root = None if sdk_root is None else Path(sdk_root).expanduser()
        self.execute = execute
        self._sdk_factory = sdk_factory

        self._gripper: Any | None = None
        self._worker: threading.Thread | None = None
        self._condition = threading.Condition()
        self._pending_position: int | None = None
        self._last_accepted_position: int | None = None
        self._last_commanded_position: int | None = None
        self._worker_error: BaseException | None = None
        self._stopping = False

    @staticmethod
    def trigger_to_position(trigger: float) -> int:
        """Map a released trigger to open and a pressed trigger to closed."""
        trigger = float(trigger)
        if not math.isfinite(trigger):
            raise DmTacClawError(f"XR trigger value is not finite: {trigger}")
        if not -0.05 <= trigger <= 1.05:
            raise DmTacClawError(f"XR trigger value is outside the valid range: {trigger}")
        trigger = min(1.0, max(0.0, trigger))
        return int(round((1.0 - trigger) * 1000.0))

    def _load_sdk_factory(self) -> Callable[..., Any]:
        if self._sdk_factory is not None:
            return self._sdk_factory
        if self.sdk_root is None:
            raise DmTacClawError(
                "DM-TacClaw SDK root is required; it must contain the gripper Python package"
            )
        package_init = self.sdk_root / "gripper" / "__init__.py"
        if not package_init.is_file():
            raise DmTacClawError(
                f"DM-TacClaw SDK package was not found at {package_init}"
            )
        sdk_root = str(self.sdk_root.resolve())
        if sdk_root not in sys.path:
            sys.path.insert(0, sdk_root)
        try:
            return importlib.import_module("gripper").Gripper
        except ModuleNotFoundError as exc:
            if exc.name in {"grpc", "google.protobuf"} or (
                exc.name is not None and exc.name.startswith("google")
            ):
                raise DmTacClawError(
                    "DM-TacClaw SDK dependencies are missing. Install the local SDK "
                    "with grpcio>=1.75.1 and protobuf>=6.32.1 in the nero environment."
                ) from exc
            raise DmTacClawError(f"Could not import the DM-TacClaw SDK: {exc}") from exc
        except (AttributeError, ImportError) as exc:
            raise DmTacClawError(f"Could not import the DM-TacClaw SDK: {exc}") from exc

    @staticmethod
    def _require_success(result: Any, operation: str) -> None:
        if result is not True:
            raise DmTacClawError(f"DM-TacClaw {operation} failed")

    def connect_and_initialize(self) -> None:
        """Connect, physically home the gripper, configure it, and open it."""
        if not self.execute:
            raise DmTacClawError(
                "DM-TacClaw initialization is forbidden outside execute mode"
            )
        if self._gripper is not None:
            return

        factory = self._load_sdk_factory()
        gripper = None
        try:
            gripper = factory(
                server_address=self.server_address,
                interface=self.remote_can_interface,
                bitrate=self.bitrate,
            )
            if getattr(gripper, "init_status", True) is not True:
                raise DmTacClawError(
                    "DM-TacClaw remote CAN initialization failed"
                )
            self._require_success(gripper.set_speed(self.speed), "speed configuration")
            self._require_success(gripper.grip_init(), "physical homing")
            self._require_success(
                gripper.set_torque_limit(self.torque_limit),
                "torque-limit configuration",
            )
            self._require_success(
                gripper.move_to_pos(self.OPEN_POSITION),
                "initial open command",
            )
        except Exception:
            if gripper is not None:
                try:
                    gripper.close()
                except Exception:
                    pass
            raise

        self._gripper = gripper
        self._last_accepted_position = self.OPEN_POSITION
        self._last_commanded_position = self.OPEN_POSITION
        self._worker = threading.Thread(
            target=self._command_worker,
            name=f"dm-tacclaw-{self.arm_name}",
            daemon=True,
        )
        self._worker.start()

    def _raise_worker_error(self) -> None:
        with self._condition:
            error = self._worker_error
        if error is not None:
            raise DmTacClawError(f"DM-TacClaw command worker failed: {error}") from error

    def command_trigger(self, trigger: float) -> int:
        position = self.trigger_to_position(trigger)
        self.command_position(position)
        return position

    def command_position(self, position: int) -> int:
        """Queue a target on the SDK's 0=closed, 1000=open position scale."""
        if self._gripper is None or self._worker is None:
            raise DmTacClawError("DM-TacClaw is not initialized")
        self._raise_worker_error()
        if isinstance(position, bool) or not isinstance(position, int):
            raise DmTacClawError("DM-TacClaw position must be an integer")
        if not self.CLOSED_POSITION <= position <= self.OPEN_POSITION:
            raise DmTacClawError(
                f"DM-TacClaw position is outside [0, 1000]: {position}"
            )
        with self._condition:
            reference = self._last_accepted_position
            if reference is not None and abs(position - reference) < self.position_deadband:
                return reference
            self._last_accepted_position = position
            self._pending_position = position
            self._condition.notify()
        return position

    def _command_worker(self) -> None:
        next_command_time = 0.0
        try:
            while True:
                with self._condition:
                    while self._pending_position is None and not self._stopping:
                        self._condition.wait()
                    if self._stopping:
                        return
                    delay = next_command_time - time.monotonic()
                    if delay > 0.0:
                        self._condition.wait(timeout=delay)
                        continue
                    position = self._pending_position
                    self._pending_position = None

                self._require_success(
                    self._gripper.move_to_pos(position),
                    f"move_to_pos({position})",
                )
                with self._condition:
                    self._last_commanded_position = position
                next_command_time = time.monotonic() + 1.0 / self.command_rate_hz
        except BaseException as exc:
            with self._condition:
                self._worker_error = exc
                self._pending_position = None
                self._condition.notify_all()

    def read_position(self) -> int:
        if self._gripper is None:
            raise DmTacClawError("DM-TacClaw is not initialized")
        self._raise_worker_error()
        position = self._gripper.read_pos()
        if isinstance(position, bool) or not isinstance(position, (int, float)):
            raise DmTacClawError(f"DM-TacClaw returned an invalid position: {position!r}")
        position = int(position)
        if not 0 <= position <= 1000:
            raise DmTacClawError(f"DM-TacClaw position is unavailable: {position}")
        return position

    @property
    def last_commanded_position(self) -> int | None:
        with self._condition:
            return self._last_commanded_position

    def close(self) -> None:
        with self._condition:
            self._stopping = True
            self._pending_position = None
            self._condition.notify_all()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
        gripper, self._gripper = self._gripper, None
        if gripper is not None:
            gripper.close()
        self._worker = None
