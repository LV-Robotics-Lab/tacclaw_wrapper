# tacclaw_wrapper

Safety-gated Python wrapper and bring-up tools for the DM TacClaw gripper and
fisheye camera. Vendor SDK drops remain untracked under `vendor/`; callers do
not import vendor modules directly.

## Ownership

- `src/tacclaw_wrapper/gripper.py`: initialization, speed/torque limits,
  bounded position commands, and deterministic shutdown.
- `src/tacclaw_wrapper/camera.py`: read-only capabilities and single-frame
  camera lifecycle.
- `src/tacclaw_wrapper/fish_camera_proxy/`: a self-hosted implementation of
  DM's documented `fish_camera.grpc_test.CameraProxy` protocol. HEVC is copied
  from V4L2 into MPEG-TS/UDP; MJPG is copied into the vendor `FCP1` UDP frame
  format. Neither path re-encodes video.
- `src/tacclaw_wrapper/worker.py`: explicitly authorized, rate-limited
  asynchronous position execution through the public gripper API.
- `src/tacclaw_wrapper/data/tacclaw_estimated_collision.yaml`: an explicitly unvalidated sphere
  fit for planning experiments; it is not measured/CAD-confirmed geometry.
- `config/dm_tacclaw.env.example`: non-secret endpoint template.
- `scripts/`: vendor extraction and Python 3.10 environment setup.
- `docs/vendor/`: the product manual migrated from the retired integration
  repository.

Tactile SDK installation is supported by the setup script, but no stable
tactile API was present in the source repository. It remains explicitly
unimplemented rather than being guessed from vendor examples.

The gripper import boundary accepts both vendor layouts retained by this
workspace.  It prefers the current product-manual API,
`dm_lingkong_grip_sdk.LingkongGrip(server_address=...)`, and falls back to the
archived `gripper.Gripper(server_address, interface, bitrate)` client.  The
constructor difference is isolated inside `vendor.py`; callers always use
`TacClawGripper`.

## Offline verification

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check src tests
.venv/bin/pytest
```

The test suite uses injected fake drivers and never opens a device.

## Vendor SDK setup

Place these user-provided archives in `vendor/source/`, or set
`DM_VENDOR_SOURCE_DIR` to their directory:

```text
gripper.zip
fish_cam.zip
SDK_Publish_V1.2.13_gripper.zip
```

Then run:

```bash
bash scripts/unpack_vendor.sh
bash scripts/setup_dm_env.sh
```

Vendor code, local endpoint configuration, virtual environments, logs, and
downloads are ignored.

## Safe smoke checks

The default commands only verify imports. They do not connect to hardware:

```bash
tacclaw-gripper-smoke --side left
tacclaw-camera-smoke --side left
```

Read-only camera access is explicit:

```bash
tacclaw-camera-smoke --side left --list-capabilities
tacclaw-camera-smoke --side left --read-once
```

## Fisheye camera board service

The vendor client archive documents a camera service on TCP port `50088`, but
the inspected TacClaw board image does not contain that service. This wrapper
includes a compatible replacement. Deploy it to both boards from the host:

```bash
bash scripts/deploy_fish_camera_servers.sh
```

The deployment installs `tacclaw-camera-server.service` under systemd and uses
the native `/dev/video4` HEVC/MJPG modes. The server permits only one active
stream per board and, by default, sends UDP only to the IP that opened the gRPC
connection. Because the boards have no Internet route, deployment uses an
ARM64 `grpcio` wheel staged in `vendor/offline-wheels/`; it does not download
packages on the boards.

Camera intrinsics are deliberately not inferred. `GetIntrinsics` returns
`FAILED_PRECONDITION` unless the server is started with `--calibration` and a
validated JSON object containing:

```json
{
  "device": "/dev/video4",
  "camera_model": "vendor-model-name",
  "distortion_model": "vendor-distortion-model",
  "intrinsics": [0.0, 0.0, 0.0, 0.0],
  "camera_matrix": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
  "distortion_coeffs": [],
  "resolution": [1280, 720],
  "sn": "optional-camera-serial"
}
```

The zeros above describe the required shape only and are not usable
calibration values.

Gripper initialization or motion requires both execution flags and a
clearance confirmation:

```bash
tacclaw-gripper-smoke --side left \
  --execute-init --execute-move --position 500 --confirm-clearance
```

This repository does not authorize Quest-driven online gripper control.
DataMaster trigger-to-position mapping is also outside this hardware wrapper;
it is implemented by `teleop_retarget`.
