#!/usr/bin/env python3
"""Compatibility entrypoint for :mod:`tacclaw_wrapper.camera_cli`."""

from tacclaw_wrapper.camera_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
