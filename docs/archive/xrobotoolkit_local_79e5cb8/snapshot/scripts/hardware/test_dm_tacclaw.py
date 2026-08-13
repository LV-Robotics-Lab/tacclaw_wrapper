"""Standalone, guarded DM-TacClaw hardware test.

The default action only checks the TCP endpoint and never constructs the
vendor SDK. Every action that can move the gripper requires MOVE_TACCLAW.
"""

from __future__ import annotations

import math
import socket
import time
from pathlib import Path
from typing import Literal

import tyro

from xrobotoolkit_teleop.hardware.interface.dm_tacclaw import (
    DmTacClawError,
    DmTacClawInterface,
)


MOVE_CONFIRMATION = "MOVE_TACCLAW"
DEFAULT_SDK_ROOT = Path(
    "/home/lvrobotics/workspace/client_V1.0.2/client_V1.0.2/gripper"
)


def _probe(host: str, port: int, timeout_s: float) -> None:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
    except OSError as exc:
        raise SystemExit(
            f"DM-TacClaw endpoint {host}:{port} is not reachable: {exc}. "
            "No SDK initialization or motion was attempted."
        ) from exc
    print(
        f"READY: DM-TacClaw gRPC TCP endpoint {host}:{port} accepts connections. "
        "No SDK initialization or motion was attempted."
    )


def _wait_for_position(
    gripper: DmTacClawInterface,
    target: int,
    *,
    timeout_s: float,
    tolerance: int,
) -> int:
    deadline = time.monotonic() + timeout_s
    stable_samples = 0
    last_position = None
    last_error = "no position feedback"
    while time.monotonic() < deadline:
        try:
            last_position = gripper.read_position()
            last_error = ""
            if abs(last_position - target) <= tolerance:
                stable_samples += 1
                if stable_samples >= 3:
                    return last_position
            else:
                stable_samples = 0
        except DmTacClawError as exc:
            if "position is unavailable" not in str(exc):
                raise
            last_error = str(exc)
            stable_samples = 0
        time.sleep(0.05)
    detail = last_error if last_position is None else f"last position={last_position}"
    raise DmTacClawError(
        f"Timed out waiting for position {target} (+/-{tolerance}); {detail}"
    )


def _run_xr_trigger(
    gripper: DmTacClawInterface,
    *,
    controller_hand: Literal["left", "right"],
    duration_s: float,
    control_rate_hz: float,
    xr_stale_timeout_s: float,
) -> None:
    from xrobotoolkit_teleop.common.xr_client import XrClient

    xr_client = XrClient()
    trigger_name = f"{controller_hand}_trigger"
    try:
        first_timestamp = xr_client.wait_for_live_controller_data()
        initial_trigger = float(xr_client.get_key_value_by_name(trigger_name))
        if not math.isfinite(initial_trigger) or not -0.05 <= initial_trigger <= 0.10:
            raise DmTacClawError(
                f"Release {trigger_name} before initialization; current value="
                f"{initial_trigger}"
            )

        print(
            "XR is ready and the trigger is released. Starting physical homing; "
            "the gripper will close, find zero, and then open."
        )
        gripper.connect_and_initialize()
        _wait_for_position(gripper, 1000, timeout_s=10.0, tolerance=15)
        print(
            f"XR control active: {trigger_name}, released=open, fully pressed=closed. "
            "Press Ctrl+C to stop."
        )

        start_time = time.monotonic()
        last_timestamp = first_timestamp
        last_timestamp_change = start_time
        last_status_time = 0.0
        period = 1.0 / control_rate_hz
        while duration_s <= 0.0 or time.monotonic() - start_time < duration_s:
            tick = time.monotonic()
            timestamp = int(xr_client.get_timestamp_ns())
            if timestamp <= 0 or timestamp < last_timestamp:
                raise DmTacClawError(f"XR timestamp is invalid: {timestamp}")
            if timestamp != last_timestamp:
                last_timestamp = timestamp
                last_timestamp_change = tick
            elif tick - last_timestamp_change > xr_stale_timeout_s:
                raise DmTacClawError("XR input timestamp is stale")

            trigger = float(xr_client.get_key_value_by_name(trigger_name))
            target = gripper.command_trigger(trigger)
            if tick - last_status_time >= 0.5:
                print(f"{trigger_name}={trigger:.3f} -> target={target}")
                last_status_time = tick
            time.sleep(max(0.0, period - (time.monotonic() - tick)))
    finally:
        xr_client.close()


def main(
    action: Literal["probe", "home", "position", "xr"] = "probe",
    host: str = "192.168.127.10",
    port: int = 55551,
    remote_can_interface: str = "can0",
    bitrate: int = 1_000_000,
    speed: int = 30,
    torque_limit: int = 30,
    command_rate_hz: float = 20.0,
    position_deadband: int = 5,
    sdk_root: str = str(DEFAULT_SDK_ROOT),
    target_position: int = 500,
    position_timeout_s: float = 10.0,
    position_tolerance: int = 15,
    controller_hand: Literal["left", "right"] = "left",
    xr_control_rate_hz: float = 50.0,
    xr_stale_timeout_s: float = 0.25,
    duration_s: float = 0.0,
    probe_timeout_s: float = 3.0,
    confirmation: str = "",
) -> None:
    """Test one DM-TacClaw without connecting to either NERO arm.

    Args:
        action: probe is read-only; home, position, and xr physically move the gripper.
        host: DM remote-CAN gRPC server address.
        port: DM remote-CAN gRPC server port.
        remote_can_interface: CAN interface name on the remote DM server.
        bitrate: CAN bitrate configured by the remote DM server.
        speed: Gripper speed in the SDK's 10..100 range.
        torque_limit: Gripper torque limit after homing, in the 10..100 range.
        command_rate_hz: Maximum outgoing gripper command rate.
        position_deadband: Minimum target change on the 0..1000 position scale.
        sdk_root: Directory containing setup.py and the gripper package.
        target_position: Position action target; 0 is closed and 1000 is open.
        position_timeout_s: Time allowed for a position to settle.
        position_tolerance: Accepted position error on the 0..1000 scale.
        controller_hand: XR action controller trigger.
        xr_control_rate_hz: XR trigger sampling rate.
        xr_stale_timeout_s: Maximum unchanged XR timestamp duration.
        duration_s: XR action duration; 0 runs until Ctrl+C.
        probe_timeout_s: TCP endpoint timeout used by the probe action.
        confirmation: Must equal MOVE_TACCLAW for every motion action.
    """
    if not 1 <= port <= 65535:
        raise SystemExit("port must be within [1, 65535]")
    if probe_timeout_s <= 0.0:
        raise SystemExit("probe_timeout_s must be positive")
    if action == "probe":
        _probe(host, port, probe_timeout_s)
        return

    if confirmation != MOVE_CONFIRMATION:
        raise SystemExit(
            "Motion was not confirmed. grip_init() physically closes the gripper "
            "to find zero. Clear the jaws and re-run with "
            f"--confirmation {MOVE_CONFIRMATION}."
        )
    if not 0 <= target_position <= 1000:
        raise SystemExit("target_position must be within [0, 1000]")
    if position_timeout_s <= 0.0 or not 0 <= position_tolerance <= 1000:
        raise SystemExit(
            "position_timeout_s must be positive and position_tolerance "
            "must be within [0, 1000]"
        )
    if xr_control_rate_hz <= 0.0 or xr_stale_timeout_s <= 0.0:
        raise SystemExit("XR rates and timeouts must be positive")
    if duration_s < 0.0:
        raise SystemExit("duration_s must be non-negative")

    gripper = DmTacClawInterface(
        arm_name="arm_a" if controller_hand == "left" else "arm_b",
        server_address=f"{host}:{port}",
        remote_can_interface=remote_can_interface,
        bitrate=bitrate,
        speed=speed,
        torque_limit=torque_limit,
        command_rate_hz=command_rate_hz,
        position_deadband=position_deadband,
        sdk_root=sdk_root,
        execute=True,
    )
    try:
        if action == "xr":
            _run_xr_trigger(
                gripper,
                controller_hand=controller_hand,
                duration_s=duration_s,
                control_rate_hz=xr_control_rate_hz,
                xr_stale_timeout_s=xr_stale_timeout_s,
            )
            return

        print(
            "Starting physical homing; the gripper will close, find zero, "
            "and then open."
        )
        gripper.connect_and_initialize()
        target = 1000 if action == "home" else target_position
        gripper.command_position(target)
        actual = _wait_for_position(
            gripper,
            target,
            timeout_s=position_timeout_s,
            tolerance=position_tolerance,
        )
        print(f"PASS: target={target}, measured={actual}")
    except KeyboardInterrupt:
        print("Operator interrupt received; closing the gripper SDK connection.")
    except DmTacClawError as exc:
        raise SystemExit(f"DM-TacClaw test failed: {exc}") from exc
    finally:
        gripper.close()


if __name__ == "__main__":
    tyro.cli(main)
