# tacclaw_wrapper

Safety-gated Python wrapper and bring-up tools for the DM TacClaw gripper and
fisheye camera. Vendor SDK drops remain untracked under `vendor/`; callers do
not import vendor modules directly.

## Ownership

- `src/tacclaw_wrapper/gripper.py`: initialization, speed/torque limits,
  bounded position commands, and deterministic shutdown.
- `src/tacclaw_wrapper/camera.py`: read-only capabilities and single-frame
  camera lifecycle.
- `config/dm_tacclaw.env.example`: non-secret endpoint template.
- `scripts/`: vendor extraction and Python 3.10 environment setup.
- `docs/vendor/`: the product manual migrated from the retired integration
  repository.

Tactile SDK installation is supported by the setup script, but no stable
tactile API was present in the source repository. It remains explicitly
unimplemented rather than being guessed from vendor examples.

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

Gripper initialization or motion requires both execution flags and a
clearance confirmation:

```bash
tacclaw-gripper-smoke --side left \
  --execute-init --execute-move --position 500 --confirm-clearance
```

This repository does not authorize Quest-driven online gripper control.
