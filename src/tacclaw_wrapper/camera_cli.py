"""Safe, read-only DM TacClaw fisheye camera smoke CLI."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .camera import CameraConfig, TacClawCamera
from .vendor import load_camera_class, resolve_vendor_root


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["left", "right"], default="left")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--codec", choices=["MJPG", "HEVC"], default="MJPG")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--client-ip", default="")
    parser.add_argument("--vendor-root", default=None)
    parser.add_argument("--list-capabilities", action="store_true")
    parser.add_argument("--read-once", action="store_true")
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        config = CameraConfig.from_env(
            args.side,
            host=args.host,
            port=args.port,
            codec=args.codec,
            width=args.width,
            height=args.height,
            fps=args.fps,
            client_ip=args.client_ip,
        )
        vendor_root = resolve_vendor_root(args.vendor_root)
        print(f"[tacclaw-camera] side={config.side} host={config.host} port={config.port}")
        camera_class = load_camera_class(vendor_root)

        if not args.list_capabilities and not args.read_once:
            print("[tacclaw-camera] dry-run import passed; no network connection attempted")
            return 0

        capabilities = TacClawCamera.capabilities(
            config, vendor_root=vendor_root, driver_factory=camera_class
        )
        print(f"[tacclaw-camera] capabilities={capabilities}")
        if not args.read_once:
            return 0

        with TacClawCamera.connect(
            config, vendor_root=vendor_root, driver_factory=camera_class
        ) as camera:
            frame = camera.read_once(timeout=args.timeout)
            print(f"[tacclaw-camera] frame shape={getattr(frame, 'shape', None)}")
        return 0
    except Exception as exc:
        print(f"[tacclaw-camera] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
