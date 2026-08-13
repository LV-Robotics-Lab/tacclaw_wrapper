"""Latest-value, rate-limited execution worker for ``TacClawGripper``.

The worker owns device lifecycle and position execution only. Mapping an input
device trigger to a TacClaw position is intentionally a teleoperation policy
and does not belong in this package.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Optional

from .gripper import MotionAuthorizationError, TacClawGripper


class TacClawWorkerState(str, Enum):
    DISABLED = "disabled"
    CONNECTING = "connecting"
    READY = "ready"
    FAULT = "fault"
    CLOSED = "closed"


class TacClawWorkerError(RuntimeError):
    pass


def _position(value: int, *, name: str = "position") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not 0 <= value <= 1000:
        raise ValueError(f"{name} must be in 0..1000")
    return value


class TacClawWorker:
    """Run blocking TacClaw SDK calls away from a teleoperation control loop."""

    def __init__(
        self,
        gripper: TacClawGripper,
        *,
        name: str,
        speed: int = 30,
        torque_limit: int = 30,
        command_rate_hz: float = 20.0,
        position_deadband: int = 5,
        initial_position: int = 1000,
    ) -> None:
        if not name:
            raise ValueError("name must not be empty")
        if not 10 <= speed <= 100 or not 10 <= torque_limit <= 100:
            raise ValueError("speed and torque_limit must be in 10..100")
        if command_rate_hz <= 0.0:
            raise ValueError("command_rate_hz must be positive")
        if not 0 <= position_deadband <= 1000:
            raise ValueError("position_deadband must be in 0..1000")

        self.gripper = gripper
        self.name = name
        self.speed = int(speed)
        self.torque_limit = int(torque_limit)
        self.command_rate_hz = float(command_rate_hz)
        self.position_deadband = int(position_deadband)
        self.initial_position = _position(initial_position, name="initial_position")

        self._condition = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        self._pending_position: Optional[int] = None
        self._last_accepted_position: Optional[int] = None
        self._last_commanded_position: Optional[int] = None
        self._state = TacClawWorkerState.DISABLED
        self._error = ""
        self._stopping = False

    @property
    def state(self) -> TacClawWorkerState:
        with self._condition:
            return self._state

    @property
    def error(self) -> str:
        with self._condition:
            return self._error

    @property
    def ready(self) -> bool:
        return self.state is TacClawWorkerState.READY

    @property
    def last_commanded_position(self) -> Optional[int]:
        with self._condition:
            return self._last_commanded_position

    def start(self, *, clearance_confirmed: bool) -> None:
        """Initialize/home asynchronously after explicit clearance approval."""

        if not clearance_confirmed:
            raise MotionAuthorizationError(
                "worker start requires explicit clearance confirmation"
            )
        with self._condition:
            if self._thread is not None:
                raise TacClawWorkerError("worker is already started")
            if self._state is not TacClawWorkerState.DISABLED:
                raise TacClawWorkerError(
                    f"worker cannot start from state {self._state.value}"
                )
            self._stopping = False
            self._error = ""
            self._state = TacClawWorkerState.CONNECTING
            self._thread = threading.Thread(
                target=self._run,
                name=f"tacclaw-{self.name}",
                daemon=True,
            )
            self._thread.start()

    def wait_ready(self, *, timeout_s: float) -> bool:
        if timeout_s <= 0.0:
            raise ValueError("timeout_s must be positive")
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while self._state is TacClawWorkerState.CONNECTING:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    break
                self._condition.wait(timeout=remaining)
            return self._state is TacClawWorkerState.READY

    def _run(self) -> None:
        try:
            self.gripper.initialize(
                speed=self.speed,
                torque=self.torque_limit,
                clearance_confirmed=True,
            )
            self.gripper.move_to_position(
                self.initial_position,
                clearance_confirmed=True,
            )
            with self._condition:
                self._last_accepted_position = self.initial_position
                self._last_commanded_position = self.initial_position
                self._state = TacClawWorkerState.READY
                self._condition.notify_all()

            next_command_time = 0.0
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

                if position is None:
                    continue
                self.gripper.move_to_position(position, clearance_confirmed=True)
                with self._condition:
                    self._last_commanded_position = position
                next_command_time = time.monotonic() + 1.0 / self.command_rate_hz
        except Exception as exc:
            with self._condition:
                self._error = str(exc)
                self._state = TacClawWorkerState.FAULT
                self._pending_position = None
                self._condition.notify_all()
        finally:
            self.gripper.close()
            with self._condition:
                if self._state is not TacClawWorkerState.FAULT:
                    self._state = TacClawWorkerState.CLOSED
                self._condition.notify_all()

    def command_position(self, position: int, *, clearance_confirmed: bool) -> int:
        if not clearance_confirmed:
            raise MotionAuthorizationError(
                "worker motion requires explicit clearance confirmation"
            )
        resolved = _position(position)
        with self._condition:
            if self._state is not TacClawWorkerState.READY:
                raise TacClawWorkerError(
                    f"worker is not ready: {self._state.value} {self._error}".rstrip()
                )
            reference = self._last_accepted_position
            if reference is not None and abs(resolved - reference) < self.position_deadband:
                return reference
            self._last_accepted_position = resolved
            self._pending_position = resolved
            self._condition.notify_all()
        return resolved

    def cancel_pending(self) -> None:
        """Discard a queued latest-value command without issuing new motion."""

        with self._condition:
            self._pending_position = None
            self._condition.notify_all()

    def close(self, *, timeout_s: float = 2.0) -> None:
        if timeout_s <= 0.0:
            raise ValueError("timeout_s must be positive")
        with self._condition:
            self._stopping = True
            self._pending_position = None
            self._condition.notify_all()
            thread = self._thread
        if thread is None:
            self.gripper.close()
            with self._condition:
                self._state = TacClawWorkerState.CLOSED
            return
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            raise TacClawWorkerError("worker did not stop before timeout")
        with self._condition:
            self._thread = None
            self._state = TacClawWorkerState.CLOSED

    def __enter__(self) -> TacClawWorker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
