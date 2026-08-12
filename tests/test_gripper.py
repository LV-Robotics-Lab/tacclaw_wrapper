from __future__ import annotations

import unittest
from typing import List, Tuple

from tacclaw_wrapper import (
    GripperConfig,
    GripperInitializationError,
    GripperNotInitializedError,
    MotionAuthorizationError,
    TacClawGripper,
)


class FakeDriver:
    def __init__(self, init_ok: bool = True):
        self.init_ok = init_ok
        self.calls: List[Tuple] = []

    def grip_init(self):
        self.calls.append(("grip_init",))
        return self.init_ok

    def set_torque_limit(self, value):
        self.calls.append(("set_torque_limit", value))

    def set_speed(self, value):
        self.calls.append(("set_speed", value))

    def move_to_pos(self, value):
        self.calls.append(("move_to_pos", value))

    def read_pos(self):
        self.calls.append(("read_pos",))
        return 503

    def close(self):
        self.calls.append(("close",))


class GripperConfigTests(unittest.TestCase):
    def test_builds_server_address_from_env(self):
        config = GripperConfig.from_env(
            "right",
            environ={
                "DM_RIGHT_HOST": "10.0.0.12",
                "DM_GRIPPER_GRPC_PORT": "55552",
            },
        )
        self.assertEqual(config.server_address, "10.0.0.12:55552")

    def test_rejects_invalid_endpoint(self):
        with self.assertRaises(ValueError):
            GripperConfig(side="middle", host="10.0.0.1")
        with self.assertRaises(ValueError):
            GripperConfig(side="left", host="", port=0)


class TacClawGripperTests(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.wrapper = TacClawGripper(
            GripperConfig(side="left", host="10.0.0.11"),
            self.driver,
        )

    def test_requires_clearance_for_initialization(self):
        with self.assertRaises(MotionAuthorizationError):
            self.wrapper.initialize(speed=30, torque=30, clearance_confirmed=False)
        self.assertEqual(self.driver.calls, [])

    def test_validates_limits_before_vendor_call(self):
        with self.assertRaises(ValueError):
            self.wrapper.initialize(speed=9, torque=30, clearance_confirmed=True)
        self.assertEqual(self.driver.calls, [])

    def test_rejects_motion_before_initialization(self):
        with self.assertRaises(GripperNotInitializedError):
            self.wrapper.move_to_position(500, clearance_confirmed=True)
        self.assertEqual(self.driver.calls, [])

    def test_initializes_moves_reads_and_closes_once(self):
        self.wrapper.initialize(speed=30, torque=40, clearance_confirmed=True)
        observed = self.wrapper.move_to_position(500, clearance_confirmed=True)
        self.wrapper.close()
        self.wrapper.close()
        self.assertEqual(observed, 503)
        self.assertEqual(
            self.driver.calls,
            [
                ("grip_init",),
                ("set_torque_limit", 40),
                ("set_speed", 30),
                ("move_to_pos", 500),
                ("read_pos",),
                ("close",),
            ],
        )

    def test_surfaces_failed_vendor_initialization(self):
        wrapper = TacClawGripper(
            GripperConfig(side="left", host="10.0.0.11"),
            FakeDriver(init_ok=False),
        )
        with self.assertRaises(GripperInitializationError):
            wrapper.initialize(speed=30, torque=30, clearance_confirmed=True)


if __name__ == "__main__":
    unittest.main()
