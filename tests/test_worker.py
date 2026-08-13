import time

import pytest

from tacclaw_wrapper import (
    GripperConfig,
    MotionAuthorizationError,
    TacClawGripper,
    TacClawWorker,
    TacClawWorkerError,
    TacClawWorkerState,
)


class FakeDriver:
    def __init__(self, *, init_ok=True) -> None:
        self.init_ok = init_ok
        self.moves = []
        self.speed = None
        self.torque = None
        self.closed = False

    def grip_init(self):
        return self.init_ok

    def set_torque_limit(self, value):
        self.torque = value

    def set_speed(self, value):
        self.speed = value

    def move_to_pos(self, value):
        self.moves.append(value)

    def read_pos(self):
        return self.moves[-1]

    def close(self):
        self.closed = True


def make_worker(*, driver=None, **overrides):
    resolved_driver = FakeDriver() if driver is None else driver
    gripper = TacClawGripper(
        GripperConfig(side="left", host="127.0.0.1"),
        resolved_driver,
    )
    options = {
        "name": "left",
        "command_rate_hz": 100.0,
    }
    options.update(overrides)
    return TacClawWorker(gripper, **options), resolved_driver


def wait_for_position(worker, position):
    deadline = time.monotonic() + 1.0
    while worker.last_commanded_position != position and time.monotonic() < deadline:
        time.sleep(0.001)


def test_worker_requires_clearance_before_homing() -> None:
    worker, driver = make_worker()
    with pytest.raises(MotionAuthorizationError):
        worker.start(clearance_confirmed=False)
    assert worker.state is TacClawWorkerState.DISABLED
    assert driver.moves == []
    worker.close()


def test_worker_homes_and_processes_positions_off_control_thread() -> None:
    worker, driver = make_worker()
    worker.start(clearance_confirmed=True)
    assert worker.wait_ready(timeout_s=1.0)
    assert worker.state is TacClawWorkerState.READY
    assert driver.moves == [1000]

    assert worker.command_position(500, clearance_confirmed=True) == 500
    wait_for_position(worker, 500)
    assert worker.last_commanded_position == 500
    assert driver.moves == [1000, 500]

    worker.close()
    assert driver.closed
    assert worker.state is TacClawWorkerState.CLOSED


def test_worker_deadband_filters_redundant_position() -> None:
    worker, driver = make_worker(position_deadband=5)
    worker.start(clearance_confirmed=True)
    assert worker.wait_ready(timeout_s=1.0)
    assert worker.command_position(998, clearance_confirmed=True) == 1000
    time.sleep(0.02)
    assert driver.moves == [1000]
    worker.close()


def test_worker_command_requires_ready_and_clearance() -> None:
    worker, _ = make_worker()
    with pytest.raises(MotionAuthorizationError):
        worker.command_position(500, clearance_confirmed=False)
    with pytest.raises(TacClawWorkerError, match="not ready"):
        worker.command_position(500, clearance_confirmed=True)
    worker.close()


def test_cancel_pending_is_a_safe_no_motion_operation() -> None:
    worker, _ = make_worker()
    worker.cancel_pending()
    assert worker.state is TacClawWorkerState.DISABLED
    worker.close()


@pytest.mark.parametrize("position", [-1, 1001, 1.5, True])
def test_worker_rejects_invalid_positions(position) -> None:
    worker, _ = make_worker()
    with pytest.raises(ValueError):
        worker.command_position(position, clearance_confirmed=True)
    worker.close()


def test_worker_surfaces_initialization_fault_and_closes() -> None:
    worker, driver = make_worker(driver=FakeDriver(init_ok=False))
    worker.start(clearance_confirmed=True)
    assert not worker.wait_ready(timeout_s=1.0)
    assert worker.state is TacClawWorkerState.FAULT
    assert "grip_init" in worker.error
    assert driver.closed
    worker.close()


def test_trigger_mapping_is_not_part_of_hardware_wrapper() -> None:
    import tacclaw_wrapper.worker as worker_module

    assert not hasattr(worker_module, "trigger_to_position")
