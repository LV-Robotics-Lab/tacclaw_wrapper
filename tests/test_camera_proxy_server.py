from __future__ import annotations

import struct
import uuid

import pytest

from tacclaw_wrapper.fish_camera_proxy import camera_proxy_pb2 as pb2
from tacclaw_wrapper.fish_camera_proxy.server import (
    CameraProxyService,
    load_intrinsics,
    peer_ip,
)
from tacclaw_wrapper.fish_camera_proxy.transport import (
    CameraMode,
    CameraProcessSession,
    StreamSpec,
    iter_mjpg_datagrams,
    parse_mode,
)

_HEADER = struct.Struct("!4sB16sQdIHHHBB")


class _Context:
    def peer(self):
        return "ipv4:192.168.127.20:43125"

    def abort(self, code, detail):
        raise RuntimeError(f"{code.name}: {detail}")


def test_vendor_descriptor_and_service_name_are_stable():
    assert pb2.DESCRIPTOR.package == "fish_camera.grpc_test"
    assert "CameraProxy" in pb2.DESCRIPTOR.services_by_name
    assert pb2.StreamEvent.STARTED == 1


def test_mjpg_datagrams_match_vendor_wire_layout():
    session_id = uuid.uuid4()
    payload = b"\xff\xd8" + bytes(range(256)) * 12 + b"\xff\xd9"
    datagrams = list(
        iter_mjpg_datagrams(
            session_id,
            42,
            payload,
            timestamp=1234.5,
            max_datagram=1200,
        )
    )
    chunks = []
    for index, datagram in enumerate(datagrams):
        header = _HEADER.unpack_from(datagram)
        assert header[0:3] == (b"FCP1", 1, session_id.bytes)
        assert header[3:6] == (42, 1234.5, len(payload))
        assert header[6:8] == (index, len(datagrams))
        assert header[9:11] == (1, 1)
        chunks.append(datagram[_HEADER.size :])
    assert b"".join(chunks) == payload


def test_mode_parser_and_ffmpeg_commands_are_native_copy_paths():
    assert parse_mode("mjpeg:1280x720@60") == CameraMode("MJPG", 1280, 720, 60)
    hevc_session = CameraProcessSession(
        StreamSpec(CameraMode("HEVC", 1280, 720, 60), "/dev/video4", "10.0.0.2", 51000)
    )
    hevc = hevc_session.build_command()
    capture = hevc_session.build_capture_command()
    mjpg = CameraProcessSession(
        StreamSpec(CameraMode("MJPG", 1280, 720, 60), "/dev/video4", "10.0.0.2", 51000)
    ).build_command()
    assert capture is not None
    assert capture[0] == "/usr/bin/v4l2-ctl"
    assert "--set-fmt-video=width=1280,height=720,pixelformat=HEVC" in capture
    assert hevc[hevc.index("-f") + 1] == "hevc"
    assert hevc[hevc.index("-c:v") + 1] == "copy"
    assert hevc[-1] == "udp://10.0.0.2:51000?pkt_size=1316"
    assert mjpg[mjpg.index("-input_format") + 1] == "mjpeg"
    assert mjpg[-3:] == ["-f", "image2pipe", "pipe:1"]


def test_capabilities_group_rates_and_validate_client_destination():
    service = CameraProxyService(
        device="/dev/video4",
        modes=(
            CameraMode("HEVC", 1280, 720, 30),
            CameraMode("HEVC", 1280, 720, 60),
            CameraMode("MJPG", 1920, 1080, 60),
        ),
        ffmpeg_bin="ffmpeg",
        calibration=None,
    )
    response = service.ListCapabilities(pb2.CapabilityRequest(), _Context())
    assert response.cameras[0].device == "/dev/video4"
    assert list(response.cameras[0].codecs[0].modes[0].fps) == [30, 60]

    request = pb2.StreamRequest(
        codec="HEVC",
        width=1280,
        height=720,
        fps=60,
        udp_port=51000,
        client_ip="192.168.127.99",
    )
    with pytest.raises(RuntimeError, match="PERMISSION_DENIED"):
        service._stream_spec(request, _Context())


def test_intrinsics_are_explicit_and_validated(tmp_path):
    assert load_intrinsics(None, "/dev/video4") is None
    calibration = tmp_path / "camera.json"
    calibration.write_text(
        """{
          "device": "/dev/video4",
          "camera_model": "fisheye",
          "distortion_model": "equidistant",
          "intrinsics": [500.0, 501.0, 640.0, 360.0],
          "camera_matrix": [500.0, 0.0, 640.0, 0.0, 501.0, 360.0, 0.0, 0.0, 1.0],
          "distortion_coeffs": [0.1, 0.01, 0.0, 0.0],
          "resolution": [1280, 720]
        }""",
        encoding="utf-8",
    )
    loaded = load_intrinsics(calibration, "/dev/video4")
    assert loaded is not None
    assert loaded["intrinsics"] == [500.0, 501.0, 640.0, 360.0]

    loaded["camera_matrix"] = [1.0]
    calibration.write_text(__import__("json").dumps(loaded), encoding="utf-8")
    with pytest.raises(ValueError, match="camera_matrix"):
        load_intrinsics(calibration, "/dev/video4")


def test_peer_ip_parses_grpc_addresses():
    assert peer_ip("ipv4:192.168.127.20:1234") == "192.168.127.20"
    assert peer_ip("ipv6:[::1]:1234") == "::1"
