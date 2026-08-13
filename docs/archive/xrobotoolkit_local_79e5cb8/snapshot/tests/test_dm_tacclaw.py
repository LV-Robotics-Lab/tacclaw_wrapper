from __future__ import annotations

import math
import time
import unittest

from xrobotoolkit_teleop.hardware.interface.dm_tacclaw import (
    DmTacClawError,
    DmTacClawInterface,
)


class FakeGripper:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.init_status = True
        self.calls = []
        self.position = 1000
        self.closed = False
        self.fail_next_move = False

    def grip_init(self):
        self.calls.append(("grip_init",))
        return True

    def set_speed(self, speed):
        self.calls.append(("set_speed", speed))
        return True

    def set_torque_limit(self, torque):
        self.calls.append(("set_torque_limit", torque))
        return True

    def move_to_pos(self, position):
        self.calls.append(("move_to_pos", position))
        if self.fail_next_move:
            self.fail_next_move = False
            raise RuntimeError("simulated RPC failure")
        self.position = position
        return True

    def read_pos(self):
        return self.position

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, **kwargs):
        instance = FakeGripper(**kwargs)
        self.instances.append(instance)
        return instance


def wait_until(predicate, timeout=0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class DmTacClawTests(unittest.TestCase):
    def make_interface(self, **kwargs):
        self.factory = FakeFactory()
        defaults = {
            "arm_name": "arm_a",
            "execute": True,
            "sdk_factory": self.factory,
            "command_rate_hz": 20.0,
            "position_deadband": 5,
        }
        defaults.update(kwargs)
        return DmTacClawInterface(**defaults)

    def test_trigger_maps_released_to_open_and_pressed_to_closed(self):
        self.assertEqual(DmTacClawInterface.trigger_to_position(0.0), 1000)
        self.assertEqual(DmTacClawInterface.trigger_to_position(0.5), 500)
        self.assertEqual(DmTacClawInterface.trigger_to_position(1.0), 0)
        self.assertEqual(DmTacClawInterface.trigger_to_position(-0.01), 1000)
        self.assertEqual(DmTacClawInterface.trigger_to_position(1.01), 0)

    def test_invalid_trigger_is_rejected(self):
        for value in (math.nan, math.inf, -0.051, 1.051):
            with self.subTest(value=value):
                with self.assertRaises(DmTacClawError):
                    DmTacClawInterface.trigger_to_position(value)

    def test_non_execute_mode_cannot_connect_or_home(self):
        interface = self.make_interface(execute=False)
        with self.assertRaisesRegex(DmTacClawError, "forbidden"):
            interface.connect_and_initialize()
        self.assertEqual(self.factory.instances, [])

    def test_initialization_homes_configures_and_opens(self):
        interface = self.make_interface(speed=30, torque_limit=30)
        try:
            interface.connect_and_initialize()
            gripper = self.factory.instances[0]
            self.assertEqual(
                gripper.kwargs,
                {
                    "server_address": "192.168.127.10:55551",
                    "interface": "can0",
                    "bitrate": 1_000_000,
                },
            )
            self.assertEqual(
                gripper.calls[:4],
                [
                    ("set_speed", 30),
                    ("grip_init",),
                    ("set_torque_limit", 30),
                    ("move_to_pos", 1000),
                ],
            )
        finally:
            interface.close()

    def test_worker_coalesces_latest_target_and_honors_deadband(self):
        interface = self.make_interface(command_rate_hz=10.0)
        try:
            interface.connect_and_initialize()
            gripper = self.factory.instances[0]
            interface.command_trigger(0.10)
            self.assertTrue(
                wait_until(
                    lambda: ("move_to_pos", 900) in gripper.calls,
                )
            )
            interface.command_trigger(0.20)
            interface.command_trigger(0.30)
            interface.command_trigger(0.301)
            self.assertTrue(
                wait_until(
                    lambda: interface.last_commanded_position == 700,
                )
            )
            worker_moves = [
                call for call in gripper.calls[4:] if call[0] == "move_to_pos"
            ]
            self.assertEqual(worker_moves, [("move_to_pos", 900), ("move_to_pos", 700)])
        finally:
            interface.close()

    def test_position_command_validates_sdk_scale(self):
        interface = self.make_interface()
        try:
            interface.connect_and_initialize()
            self.assertEqual(interface.command_position(500), 500)
            for invalid in (-1, 1001, 1.5, True):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(DmTacClawError):
                        interface.command_position(invalid)
        finally:
            interface.close()

    def test_worker_error_is_reported_on_next_control_sample(self):
        interface = self.make_interface()
        try:
            interface.connect_and_initialize()
            gripper = self.factory.instances[0]
            gripper.fail_next_move = True
            interface.command_trigger(1.0)
            self.assertTrue(wait_until(lambda: gripper.fail_next_move is False))
            with self.assertRaisesRegex(DmTacClawError, "simulated RPC failure"):
                interface.command_trigger(0.5)
        finally:
            interface.close()

    def test_read_position_rejects_sdk_error_sentinel(self):
        interface = self.make_interface()
        try:
            interface.connect_and_initialize()
            self.factory.instances[0].position = -1
            with self.assertRaisesRegex(DmTacClawError, "unavailable"):
                interface.read_position()
        finally:
            interface.close()

    def test_close_stops_worker_and_closes_sdk(self):
        interface = self.make_interface()
        interface.connect_and_initialize()
        gripper = self.factory.instances[0]
        worker = interface._worker

        interface.close()

        self.assertFalse(worker.is_alive())
        self.assertTrue(gripper.closed)


if __name__ == "__main__":
    unittest.main()
