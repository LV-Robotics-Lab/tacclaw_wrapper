# LV Robotics TacClaw vendor-download archive (2026-08-15)

The three vendor drops formerly staged in `/home/lvrobotics/Downloads` are
retained byte-for-byte in the shared NAS beside this repository:

```text
/mnt/workspace/tacclaw_wrapper/vendor/archive/
  lvrobotics-downloads-20260815/
    SDK_Publish_V1.2.13_gripper/
    TacClaw SDK/
    TacClaw说明书/
```

The destination is below the ignored `vendor/` boundary. The repository is
public, so vendor binaries, obfuscated SDK code, original ZIP files, and PDF
manuals are deliberately not committed as Git objects.

## Snapshot inventory

| Source group | Files | Regular-file bytes |
| --- | ---: | ---: |
| `SDK_Publish_V1.2.13_gripper` | 93 | 734,835,228 |
| `TacClaw SDK` | 20 | 1,329,164,691 |
| `TacClaw说明书` | 4 | 7,559,790 |
| **Total** | **117** | **2,071,559,709** |

The complete relative-path manifest is stored as
`.asset-manifest.sha256` in the NAS archive. Its own SHA-256 is
`262bba9541441efe99d17bdf3a95559804a57cb306b6c4b551486ab61142c1e5`.

The maintained wrapper already separates vendor payloads from the public API:
`scripts/unpack_vendor.sh` consumes `gripper.zip`, `fish_cam.zip`, and
`SDK_Publish_V1.2.13_gripper.zip` from an ignored vendor source directory,
while `src/tacclaw_wrapper/` owns the safety gates and import boundary. The
product manual suitable for source control is already preserved as Markdown
under `docs/vendor/`; original PDFs remain in the NAS snapshot.

## Verification and deletion gate

The manifest was generated from the source with relative paths, and an
independent manifest was generated from the NAS copy. The three source
directories may be deleted only after the manifests compare byte-for-byte,
the group counts and byte totals match, this migration record is merged to
`main`, and no process has a working directory or open file under them.
