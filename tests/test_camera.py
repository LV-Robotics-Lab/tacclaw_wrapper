from __future__ import annotations

import unittest

from tacclaw_wrapper import CameraConfig, CameraReadError, TacClawCamera


class FakeCapture:
    listed = []

    @classmethod
    def list_capabilities(cls, host, *, port):
        cls.listed.append((host, port))
        return {"codecs": ["MJPG"]}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.read_result = (True, "frame")

    def open(self):
        self.calls.append(("open",))

    def read(self, *, timeout):
        self.calls.append(("read", timeout))
        return self.read_result

    def get(self, name):
        return "fake-error" if name == "error" else None

    def release(self):
        self.calls.append(("release",))


class CameraConfigTests(unittest.TestCase):
    def test_builds_endpoint_from_side_environment(self):
        config = CameraConfig.from_env(
            "right",
            environ={"DM_RIGHT_HOST": "10.0.0.12", "DM_FISH_CAMERA_GRPC_PORT": "50089"},
        )
        self.assertEqual(config.host, "10.0.0.12")
        self.assertEqual(config.port, 50089)

    def test_rejects_invalid_stream_settings(self):
        with self.assertRaises(ValueError):
            CameraConfig(side="middle", host="10.0.0.1")
        with self.assertRaises(ValueError):
            CameraConfig(side="left", host="", codec="RAW")


class TacClawCameraTests(unittest.TestCase):
    def setUp(self):
        self.config = CameraConfig(side="left", host="10.0.0.11")

    def test_lists_capabilities_without_constructing_capture(self):
        observed = TacClawCamera.capabilities(
            self.config,
            vendor_root=None,
            driver_factory=FakeCapture,
        )
        self.assertEqual(observed, {"codecs": ["MJPG"]})
        self.assertEqual(FakeCapture.listed[-1], ("10.0.0.11", 50088))

    def test_reads_one_frame_and_releases_once(self):
        camera = TacClawCamera.connect(
            self.config,
            vendor_root=None,
            driver_factory=FakeCapture,
        )
        with camera:
            self.assertEqual(camera.read_once(timeout=1.5), "frame")
        camera.close()
        self.assertEqual(
            camera._capture.calls,
            [("open",), ("read", 1.5), ("release",)],
        )

    def test_rejects_read_before_open_and_vendor_failure(self):
        camera = TacClawCamera.connect(
            self.config,
            vendor_root=None,
            driver_factory=FakeCapture,
        )
        with self.assertRaises(CameraReadError):
            camera.read_once()
        camera.open()
        camera._capture.read_result = (False, None)
        with self.assertRaisesRegex(CameraReadError, "fake-error"):
            camera.read_once()


if __name__ == "__main__":
    unittest.main()
