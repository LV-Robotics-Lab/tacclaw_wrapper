from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tacclaw_wrapper.vendor import create_gripper_driver


class RecordingFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return kwargs


def test_current_manual_sdk_receives_only_server_address() -> None:
    factory = RecordingFactory()
    with patch(
        "tacclaw_wrapper.vendor._load_gripper_backend",
        return_value=(factory, "lingkong"),
    ):
        driver = create_gripper_driver(
            Path("/unused"),
            server_address="192.168.127.10:55551",
            interface="can0",
            bitrate=1_000_000,
        )

    assert driver == {"server_address": "192.168.127.10:55551"}
    assert factory.calls == [{"server_address": "192.168.127.10:55551"}]


def test_legacy_sdk_retains_remote_can_constructor_arguments() -> None:
    factory = RecordingFactory()
    with patch(
        "tacclaw_wrapper.vendor._load_gripper_backend",
        return_value=(factory, "legacy_remote_can"),
    ):
        driver = create_gripper_driver(
            Path("/unused"),
            server_address="192.168.127.10:55551",
            interface="can7",
            bitrate=500_000,
        )

    assert driver == {
        "server_address": "192.168.127.10:55551",
        "interface": "can7",
        "bitrate": 500_000,
    }
    assert factory.calls == [driver]
