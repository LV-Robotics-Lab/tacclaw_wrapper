# Yuhang TacClaw host migration (2026-08-13)

The non-Git directory `/home/feibo/TacClaw` on the Yuhang workstation was
audited before consolidation into this repository.

## Promoted to maintained source

- `scripts/backpack_data.sh`: read-only backpack status, episode listing, and
  download.
- `scripts/export_backpack_data.sh`: checksum-verified export with guarded
  removal of a verified remote episode.
- `scripts/validate_backpack_episode.py`: standalone episode validator.
- `docs/operations/backpack_data.md`: networking and operational instructions.

The validator is covered by offline tests. The shell scripts pass Bash syntax
checks; hardware and backpack access are intentionally not exercised by CI.

## Preserved locally, excluded from Git

The source directory also contained real dual-claw captures, vendor sample
captures, and PDF manuals. Captures embed camera and gripper serial numbers,
episode UUIDs, and real video. These artifacts were kept on the workstation
under the ignored `local_data/` directory with a SHA-256 manifest; they were not
published in the repository history.

## Not migrated as source

- The top-level README was a copy of the public Daimon-Infinity dataset page,
  not TacClaw wrapper documentation.
- Two Codex session transcripts were debugging logs, not maintained code. They
  included authentication prompts and were excluded from the repository.
- Python bytecode was generated cache material.

The operational behavior needed from those sessions is represented by the
maintained scripts and documentation above.
