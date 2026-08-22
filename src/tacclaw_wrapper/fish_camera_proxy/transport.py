"""V4L2/FFmpeg capture and UDP transport for the camera proxy."""

from __future__ import annotations

import socket
import struct
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence

_HEADER = struct.Struct("!4sB16sQdIHHHBB")
_MAGIC = b"FCP1"
_VERSION = 1
_MJPG_CODEC = 1
_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"


@dataclass(frozen=True)
class CameraMode:
    codec: str
    width: int
    height: int
    fps: int

    def __post_init__(self) -> None:
        codec = self.codec.upper()
        if codec == "MJPEG":
            codec = "MJPG"
        if codec not in {"HEVC", "MJPG"}:
            raise ValueError(f"unsupported codec: {self.codec}")
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("mode width, height, and fps must be positive")
        object.__setattr__(self, "codec", codec)


@dataclass(frozen=True)
class StreamSpec:
    mode: CameraMode
    device: str
    client_ip: str
    udp_port: int
    max_datagram: int = 1200

    def __post_init__(self) -> None:
        if not 1 <= self.udp_port <= 65535:
            raise ValueError("udp_port must be in 1..65535")
        if not 576 <= self.max_datagram <= 65507:
            raise ValueError("max_datagram must be in 576..65507")


def parse_mode(value: str) -> CameraMode:
    try:
        codec, dimensions = value.split(":", 1)
        resolution, fps_text = dimensions.split("@", 1)
        width_text, height_text = resolution.lower().split("x", 1)
        return CameraMode(codec, int(width_text), int(height_text), int(fps_text))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid camera mode {value!r}; expected CODEC:WIDTHxHEIGHT@FPS"
        ) from exc


def iter_mjpg_datagrams(
    session_id: uuid.UUID,
    frame_id: int,
    payload: bytes,
    *,
    timestamp: float,
    max_datagram: int,
) -> Iterable[bytes]:
    max_payload = max_datagram - _HEADER.size
    if max_payload <= 0:
        raise ValueError(f"max_datagram must exceed header size {_HEADER.size}")
    chunk_count = max(1, (len(payload) + max_payload - 1) // max_payload)
    if chunk_count > 0xFFFF:
        raise ValueError("MJPG frame needs more than 65535 UDP chunks")
    for chunk_index in range(chunk_count):
        start = chunk_index * max_payload
        chunk = payload[start : start + max_payload]
        yield _HEADER.pack(
            _MAGIC,
            _VERSION,
            session_id.bytes,
            frame_id,
            timestamp,
            len(payload),
            chunk_index,
            chunk_count,
            len(chunk),
            _MJPG_CODEC,
            1,
        ) + chunk


class CameraProcessSession:
    """One native camera capture pipeline and its UDP destination."""

    def __init__(
        self,
        spec: StreamSpec,
        *,
        ffmpeg_bin: str = "/usr/bin/ffmpeg",
        v4l2_ctl_bin: str = "/usr/bin/v4l2-ctl",
        popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        self.spec = spec
        self.ffmpeg_bin = ffmpeg_bin
        self.v4l2_ctl_bin = v4l2_ctl_bin
        self.session_uuid = uuid.uuid4()
        self.session_id = str(self.session_uuid)
        self.frames_sent = 0
        self.bytes_sent = 0
        self.started_monotonic = 0.0
        self.error: Optional[str] = None
        self.stderr_tail = ""

        self._popen_factory = popen_factory
        self._proc: Optional[subprocess.Popen] = None
        self._capture_proc: Optional[subprocess.Popen] = None
        self._socket: Optional[socket.socket] = None
        self._worker: Optional[threading.Thread] = None
        self._stderr_worker: Optional[threading.Thread] = None
        self._capture_stderr_worker: Optional[threading.Thread] = None
        self._capture_stderr_tail = ""
        self._stop = threading.Event()
        self.finished = threading.Event()
        self._stop_lock = threading.Lock()

    @property
    def elapsed_sec(self) -> float:
        if not self.started_monotonic:
            return 0.0
        return max(0.0, time.monotonic() - self.started_monotonic)

    def build_command(self) -> List[str]:
        mode = self.spec.mode
        if mode.codec == "HEVC":
            return [
                self.ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "warning",
                "-r",
                str(mode.fps),
                "-f",
                "hevc",
                "-i",
                "pipe:0",
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "copy",
                "-f",
                "mpegts",
                "-mpegts_flags",
                "+resend_headers",
                "-flush_packets",
                "1",
                "-stats_period",
                "1",
                "-progress",
                "pipe:1",
                "-nostats",
                f"udp://{self.spec.client_ip}:{self.spec.udp_port}?pkt_size=1316",
            ]
        return [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-video_size",
            f"{mode.width}x{mode.height}",
            "-framerate",
            str(mode.fps),
            "-i",
            self.spec.device,
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            "-f",
            "image2pipe",
            "pipe:1",
        ]

    def build_capture_command(self) -> Optional[List[str]]:
        mode = self.spec.mode
        if mode.codec != "HEVC":
            return None
        return [
            self.v4l2_ctl_bin,
            f"--device={self.spec.device}",
            (
                f"--set-fmt-video=width={mode.width},height={mode.height},"
                "pixelformat=HEVC"
            ),
            f"--set-parm={mode.fps}",
            "--stream-mmap=4",
            "--stream-to=-",
        ]

    def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError("camera session was already started")
        if self.spec.mode.codec == "MJPG":
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.connect((self.spec.client_ip, self.spec.udp_port))
            proc_stdin = subprocess.DEVNULL
        else:
            capture_command = self.build_capture_command()
            assert capture_command is not None
            self._capture_proc = self._popen_factory(
                capture_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=True,
            )
            assert self._capture_proc.stdout is not None
            proc_stdin = self._capture_proc.stdout
        try:
            self._proc = self._popen_factory(
                self.build_command(),
                stdin=proc_stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=True,
            )
        except Exception:
            self._terminate_process(self._capture_proc)
            raise
        finally:
            if self._capture_proc is not None and self._capture_proc.stdout is not None:
                self._capture_proc.stdout.close()
        self.started_monotonic = time.monotonic()
        self._stderr_worker = threading.Thread(
            target=self._read_stderr,
            args=(self._proc, False),
            daemon=True,
        )
        self._stderr_worker.start()
        if self._capture_proc is not None:
            self._capture_stderr_worker = threading.Thread(
                target=self._read_stderr,
                args=(self._capture_proc, True),
                daemon=True,
            )
            self._capture_stderr_worker.start()
        target = self._run_hevc if self.spec.mode.codec == "HEVC" else self._run_mjpg
        self._worker = threading.Thread(target=target, daemon=True)
        self._worker.start()

    def _read_stderr(self, proc: Optional[subprocess.Popen], capture: bool) -> None:
        if proc is None or proc.stderr is None:
            return
        tail = bytearray()
        while not self._stop.is_set():
            chunk = proc.stderr.read(4096)
            if not chunk:
                break
            tail.extend(chunk)
            if len(tail) > 32768:
                del tail[:-32768]
        text = tail.decode("utf-8", errors="replace").strip()
        if capture:
            self._capture_stderr_tail = text
        else:
            self.stderr_tail = text

    def _run_hevc(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        try:
            for raw_line in iter(proc.stdout.readline, b""):
                if self._stop.is_set():
                    break
                key, separator, value = raw_line.decode("utf-8", errors="replace").partition("=")
                if not separator:
                    continue
                value = value.strip()
                if key == "frame" and value.isdigit():
                    self.frames_sent = int(value)
                elif key == "total_size" and value.isdigit():
                    self.bytes_sent = int(value)
            self._record_unexpected_exit()
        except Exception as exc:
            if not self._stop.is_set():
                self.error = f"HEVC stream failed: {exc}"
        finally:
            self.finished.set()

    def _run_mjpg(self) -> None:
        proc = self._proc
        sock = self._socket
        assert proc is not None and proc.stdout is not None and sock is not None
        buffer = bytearray()
        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                buffer.extend(chunk)
                self._send_complete_jpegs(buffer, sock)
                if len(buffer) > 16 * 1024 * 1024:
                    raise RuntimeError("MJPG parser exceeded its 16 MiB frame buffer")
            self._record_unexpected_exit()
        except Exception as exc:
            if not self._stop.is_set():
                self.error = f"MJPG stream failed: {exc}"
        finally:
            self.finished.set()

    def _send_complete_jpegs(self, buffer: bytearray, sock: socket.socket) -> None:
        while True:
            start = buffer.find(_JPEG_SOI)
            if start < 0:
                if buffer[-1:] != _JPEG_SOI[:1]:
                    buffer.clear()
                return
            if start:
                del buffer[:start]
            end = buffer.find(_JPEG_EOI, 2)
            if end < 0:
                return
            end += len(_JPEG_EOI)
            frame = bytes(buffer[:end])
            del buffer[:end]
            self.frames_sent += 1
            for datagram in iter_mjpg_datagrams(
                self.session_uuid,
                self.frames_sent,
                frame,
                timestamp=time.time(),
                max_datagram=self.spec.max_datagram,
            ):
                sock.send(datagram)
                self.bytes_sent += len(datagram)

    def _record_unexpected_exit(self) -> None:
        proc = self._proc
        if proc is None or self._stop.is_set():
            return
        return_code = proc.wait()
        details = [value for value in (self.stderr_tail, self._capture_stderr_tail) if value]
        detail = f": {'; '.join(details)}" if details else ""
        self.error = f"ffmpeg exited with status {return_code}{detail}"

    @staticmethod
    def _terminate_process(proc: Optional[subprocess.Popen]) -> None:
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)

    def stop(self) -> None:
        with self._stop_lock:
            self._stop.set()
            self._terminate_process(self._capture_proc)
            self._terminate_process(self._proc)
            if self._socket is not None:
                self._socket.close()
                self._socket = None
        current = threading.current_thread()
        for worker in (self._worker, self._stderr_worker, self._capture_stderr_worker):
            if worker is not None and worker is not current and worker.is_alive():
                worker.join(timeout=1.0)
        self.finished.set()


def group_modes(modes: Sequence[CameraMode]):
    grouped = {}
    for mode in modes:
        resolutions = grouped.setdefault(mode.codec, {})
        resolutions.setdefault((mode.width, mode.height), []).append(mode.fps)
    return grouped
