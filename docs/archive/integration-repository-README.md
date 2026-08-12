# DM TacClaw

Status: `NOT_STARTED`. The files in this directory are compatibility bring-up
commands, not an accepted online gripper adapter. New integration code must use
the sibling `tacclaw_wrapper` package rather than importing vendor SDK modules
directly.

This directory owns DM TacClaw gripper, fisheye camera, and tactile SDK
bring-up. Keep it isolated from Quest and NERO ROS environments.

Vendor drops:

```text
client_V1.0.2/gripper.zip
client_V1.0.2/fish_cam.zip
client_V1.0.2/SDK_Publish_V1.2.13_gripper.zip
```

First commands:

```bash
bash dm-tacclaw/scripts/unpack_vendor.sh
bash dm-tacclaw/scripts/setup_dm_env.sh
```

Verify both physical IP/port sets before running a client. Camera and tactile
checks are read-only first. Gripper scripts default to dry-run. Real gripper motion requires explicit
`--execute-init` or `--execute-move` plus `--confirm-clearance`.
