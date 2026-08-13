# XRoboToolkit local TacClaw snapshot

This directory preserves the TacClaw-owned portion of the uncommitted
`XRoboToolkit-Teleop-Sample-Python` worktree found on 2026-08-13. Its upstream
baseline was commit `79e5cb8a56e3455515ce1b476e993c764ec58739`.

The three files under `snapshot/` are byte-for-byte copies of the local
DataMaster/TacClaw interface, smoke script, and tests. They are recovery
evidence rather than a second maintained implementation. The supported API is
the safety-gated `tacclaw_wrapper` package.

`manifest.sha256` is sorted by snapshot-relative path and is the deletion audit
boundary for this portion of the retired worktree.
