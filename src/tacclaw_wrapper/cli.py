"""Compatibility CLI for the first DM TacClaw gripper smoke gate."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .config import GripperConfig
from .gripper import TacClawGripper
from .vendor import load_gripper_class, resolve_vendor_root


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe DM TacClaw gripper smoke helper.")
    parser.add_argument("--side", choices=["left", "right"], default="left")
    parser.add_argument("--host", default=None)
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DM_GRIPPER_GRPC_PORT", "55551")),
    )
    parser.add_argument("--interface", default="can0")
    parser.add_argument("--bitrate", type=int, default=1_000_000)
    parser.add_argument("--vendor-root", default=None)
    parser.add_argument(
        "--speed", type=int, default=int(os.environ.get("DM_DEFAULT_SPEED", "30"))
    )
    parser.add_argument(
        "--torque", type=int, default=int(os.environ.get("DM_DEFAULT_TORQUE", "30"))
    )
    parser.add_argument(
        "--position",
        type=int,
        default=int(os.environ.get("DM_POS_HALF_OPEN", "500")),
    )
    parser.add_argument("--execute-init", action="store_true")
    parser.add_argument("--execute-move", action="store_true")
    parser.add_argument("--confirm-clearance", action="store_true")
    return parser.parse_args(argv)


def main(
    argv: Optional[List[str]] = None,
    *,
    repo_root: Optional[Path] = None,
) -> int:
    args = parse_args(argv)
    try:
        config = GripperConfig.from_env(
            args.side,
            host=args.host,
            port=args.port,
            interface=args.interface,
            bitrate=args.bitrate,
        )
        vendor_root = resolve_vendor_root(args.vendor_root, repo_root=repo_root)

        print(f"[tacclaw-gripper] side={config.side} server={config.server_address}")
        print(
            f"[tacclaw-gripper] speed={args.speed} torque={args.torque} "
            f"position={args.position}"
        )

        if not args.execute_init and not args.execute_move:
            load_gripper_class(vendor_root)
            print(
                "[tacclaw-gripper] dry-run only. Import succeeded; "
                "no connection or motion attempted."
            )
            return 0

        if not args.confirm_clearance:
            raise ValueError("refusing execution without --confirm-clearance")
        if args.execute_move and not args.execute_init:
            raise ValueError(
                "refusing --execute-move without --execute-init for first smoke tests"
            )

        gripper = TacClawGripper.connect(config, vendor_root=vendor_root)
        try:
            gripper.initialize(
                speed=args.speed,
                torque=args.torque,
                clearance_confirmed=args.confirm_clearance,
            )
            print("[tacclaw-gripper] grip_init passed")
            if args.execute_move:
                read_position = gripper.move_to_position(
                    args.position,
                    clearance_confirmed=args.confirm_clearance,
                )
                print(f"[tacclaw-gripper] commanded position {args.position}")
                print(f"[tacclaw-gripper] read_pos={read_position}")
            return 0
        finally:
            gripper.close()
    except Exception as exc:
        print(f"[tacclaw-gripper] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
