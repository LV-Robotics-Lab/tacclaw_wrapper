"""gRPC control server compatible with DM's RemoteCameraCapture client."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import shutil
import signal
import threading
from concurrent import futures
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

import grpc

from . import camera_proxy_pb2 as pb2
from . import camera_proxy_pb2_grpc as pb2_grpc
from .transport import CameraMode, CameraProcessSession, StreamSpec, group_modes, parse_mode

DEFAULT_MODES = (
    CameraMode("HEVC", 1280, 720, 60),
    CameraMode("HEVC", 1920, 1080, 60),
    CameraMode("MJPG", 1280, 720, 60),
    CameraMode("MJPG", 1920, 1080, 60),
)


def peer_ip(peer: str) -> str:
    if peer.startswith("ipv4:"):
        return peer[5:].rsplit(":", 1)[0]
    if peer.startswith("ipv6:"):
        value = peer[5:].rsplit(":", 1)[0]
        return value[1:-1] if value.startswith("[") and value.endswith("]") else value
    raise ValueError(f"unsupported gRPC peer address: {peer}")


def read_usb_serial(device: str, *, sys_class_root: Path = Path("/sys/class/video4linux")) -> str:
    device_name = Path(device).name
    sys_device = sys_class_root / device_name / "device"
    try:
        current = sys_device.resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        return ""
    for candidate in (current, *current.parents):
        serial_path = candidate / "serial"
        try:
            serial = serial_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if serial:
            return serial
    return ""


def load_intrinsics(path: Optional[Path], device: str) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load camera calibration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("camera calibration root must be an object")
    required = {
        "camera_model": str,
        "distortion_model": str,
        "intrinsics": list,
        "camera_matrix": list,
        "distortion_coeffs": list,
        "resolution": list,
    }
    for name, expected_type in required.items():
        if not isinstance(value.get(name), expected_type):
            raise ValueError(f"camera calibration field {name!r} must be {expected_type.__name__}")
    if len(value["intrinsics"]) != 4:
        raise ValueError("camera calibration intrinsics must contain [fx, fy, cx, cy]")
    if len(value["camera_matrix"]) != 9:
        raise ValueError("camera calibration camera_matrix must contain 9 values")
    if len(value["resolution"]) != 2:
        raise ValueError("camera calibration resolution must contain [width, height]")
    numeric_fields = ("intrinsics", "camera_matrix", "distortion_coeffs", "resolution")
    for field in numeric_fields:
        if not all(isinstance(item, (int, float)) and math.isfinite(item) for item in value[field]):
            raise ValueError(f"camera calibration field {field!r} must contain finite numbers")
    configured_device = str(value.get("device", device))
    if configured_device != device:
        raise ValueError(
            f"camera calibration device {configured_device!r} does not match "
            f"server device {device!r}"
        )
    value["device"] = configured_device
    return value


class CameraProxyService(pb2_grpc.CameraProxyServicer):
    def __init__(
        self,
        *,
        device: str,
        modes: Sequence[CameraMode],
        ffmpeg_bin: str,
        calibration: Optional[Dict[str, Any]],
        v4l2_ctl_bin: str = "/usr/bin/v4l2-ctl",
        allow_client_forwarding: bool = False,
        session_factory: Callable[..., CameraProcessSession] = CameraProcessSession,
    ) -> None:
        if not modes:
            raise ValueError("at least one camera mode is required")
        self.device = device
        self.modes = tuple(modes)
        self.ffmpeg_bin = ffmpeg_bin
        self.v4l2_ctl_bin = v4l2_ctl_bin
        self.calibration = calibration
        self.allow_client_forwarding = allow_client_forwarding
        self._session_factory = session_factory
        self._lock = threading.Lock()
        self._active: Optional[CameraProcessSession] = None

    def _validate_device(self, requested: str, context) -> None:
        if requested and requested != self.device:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"this server exposes only {self.device}, not {requested}",
            )

    def ListCapabilities(self, request, context):
        self._validate_device(request.device, context)
        camera = pb2.CameraCapability(device=self.device)
        for codec, resolutions in sorted(group_modes(self.modes).items()):
            codec_message = camera.codecs.add(codec=codec)
            for (width, height), rates in sorted(resolutions.items()):
                codec_message.modes.add(width=width, height=height, fps=sorted(set(rates)))
        return pb2.CapabilityResponse(cameras=[camera])

    def GetSN(self, request, context):
        self._validate_device(request.device, context)
        serial = read_usb_serial(self.device)
        return pb2.SNResponse(device=self.device, sn=serial, valid=bool(serial))

    def GetIntrinsics(self, request, context):
        self._validate_device(request.device, context)
        if self.calibration is None:
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "camera calibration is unavailable; configure --calibration "
                "with a validated JSON file",
            )
        assert self.calibration is not None
        serial = str(self.calibration.get("sn", "")) or read_usb_serial(self.device)
        return pb2.IntrinsicsResponse(
            device=self.device,
            camera_model=self.calibration["camera_model"],
            distortion_model=self.calibration["distortion_model"],
            intrinsics=self.calibration["intrinsics"],
            camera_matrix=self.calibration["camera_matrix"],
            distortion_coeffs=self.calibration["distortion_coeffs"],
            resolution=self.calibration["resolution"],
            sn=serial,
            sn_valid=bool(serial),
            camera_model_enum=int(self.calibration.get("camera_model_enum", 0)),
        )

    def _stream_spec(self, request, context) -> StreamSpec:
        self._validate_device(request.device, context)
        codec = request.codec.upper()
        if codec == "MJPEG":
            codec = "MJPG"
        try:
            requested = CameraMode(codec, request.width, request.height, request.fps)
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("context.abort unexpectedly returned") from exc
        if requested not in self.modes:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"unsupported stream mode {codec}:{request.width}x{request.height}@{request.fps}",
            )
        try:
            remote_ip = peer_ip(context.peer())
            ipaddress.ip_address(remote_ip)
            client_ip = request.client_ip or remote_ip
            ipaddress.ip_address(client_ip)
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        if not self.allow_client_forwarding and client_ip != remote_ip:
            context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                f"UDP client_ip {client_ip} does not match gRPC peer {remote_ip}",
            )
        try:
            return StreamSpec(
                mode=requested,
                device=self.device,
                client_ip=client_ip,
                udp_port=request.udp_port,
                max_datagram=request.max_datagram or 1200,
            )
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("context.abort unexpectedly returned") from exc

    @staticmethod
    def _event(session: CameraProcessSession, event_type: int, message: str):
        mode = session.spec.mode
        return pb2.StreamEvent(
            type=event_type,
            session_id=session.session_id,
            message=message,
            codec=mode.codec,
            width=mode.width,
            height=mode.height,
            fps=mode.fps,
            device=session.spec.device,
            frames_sent=session.frames_sent,
            bytes_sent=session.bytes_sent,
            elapsed_sec=session.elapsed_sec,
        )

    def OpenStream(self, request, context):
        spec = self._stream_spec(request, context)
        session = self._session_factory(
            spec,
            ffmpeg_bin=self.ffmpeg_bin,
            v4l2_ctl_bin=self.v4l2_ctl_bin,
        )
        with self._lock:
            if self._active is not None:
                context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    f"camera already has active session {self._active.session_id}",
                )
            self._active = session
        try:
            session.start()
            yield self._event(session, pb2.StreamEvent.STARTED, "camera stream started")
            while context.is_active() and not session.finished.wait(timeout=1.0):
                yield self._event(session, pb2.StreamEvent.STATS, "camera stream active")
            if session.error:
                yield self._event(session, pb2.StreamEvent.ERROR, session.error)
            elif context.is_active():
                yield self._event(session, pb2.StreamEvent.STOPPED, "camera stream stopped")
        except (OSError, RuntimeError) as exc:
            yield self._event(session, pb2.StreamEvent.ERROR, f"cannot start camera stream: {exc}")
        finally:
            session.stop()
            with self._lock:
                if self._active is session:
                    self._active = None

    def StopStream(self, request, context):
        with self._lock:
            session = self._active
        if session is None:
            return pb2.StopStreamResponse(stopped=False, message="no active camera stream")
        if request.session_id and request.session_id != session.session_id:
            return pb2.StopStreamResponse(
                stopped=False,
                message=f"active session is {session.session_id}, not {request.session_id}",
            )
        session.stop()
        return pb2.StopStreamResponse(stopped=True, message="camera stream stopped")

    def close(self) -> None:
        with self._lock:
            session = self._active
        if session is not None:
            session.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0:50088")
    parser.add_argument("--device", default="/dev/video4")
    parser.add_argument("--ffmpeg-bin", default="/usr/bin/ffmpeg")
    parser.add_argument("--v4l2-ctl-bin", default="/usr/bin/v4l2-ctl")
    parser.add_argument("--calibration", type=Path)
    parser.add_argument(
        "--mode",
        action="append",
        type=parse_mode,
        help="advertised native mode, e.g. HEVC:1280x720@60; repeat as needed",
    )
    parser.add_argument(
        "--allow-client-forwarding",
        action="store_true",
        help="allow UDP destinations other than the gRPC peer (disabled by default)",
    )
    parser.add_argument("--workers", type=int, default=4)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not Path(args.device).is_char_device():
        raise SystemExit(f"camera device is missing or is not a character device: {args.device}")
    if not (Path(args.ffmpeg_bin).is_file() or shutil.which(args.ffmpeg_bin)):
        raise SystemExit(f"ffmpeg executable was not found: {args.ffmpeg_bin}")
    if not (Path(args.v4l2_ctl_bin).is_file() or shutil.which(args.v4l2_ctl_bin)):
        raise SystemExit(f"v4l2-ctl executable was not found: {args.v4l2_ctl_bin}")
    if args.workers < 2:
        raise SystemExit("--workers must be at least 2 so StopStream cannot deadlock")
    calibration = load_intrinsics(args.calibration, args.device)
    service = CameraProxyService(
        device=args.device,
        modes=args.mode or DEFAULT_MODES,
        ffmpeg_bin=args.ffmpeg_bin,
        v4l2_ctl_bin=args.v4l2_ctl_bin,
        calibration=calibration,
        allow_client_forwarding=args.allow_client_forwarding,
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=args.workers))
    pb2_grpc.add_CameraProxyServicer_to_server(service, server)
    bound_port = server.add_insecure_port(args.bind)
    if not bound_port:
        raise SystemExit(f"failed to bind camera proxy to {args.bind}")

    stopping = threading.Event()

    def stop_server(_signum=None, _frame=None):
        if stopping.is_set():
            return
        stopping.set()
        service.close()
        server.stop(grace=2.0)

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)
    server.start()
    print(f"TacClaw camera proxy listening on {args.bind}, device={args.device}", flush=True)
    server.wait_for_termination()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
