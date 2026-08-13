# DataMaster integration split

The legacy NERO/DataMaster integration contained an asynchronous TacClaw worker and a `trigger_to_position` mapping in the same module.

This repository now owns only the hardware-facing worker:

- explicit clearance approval before homing/initial positioning
- latest-value queueing and command-rate limiting
- position deadband
- deterministic driver closure and surfaced fault state
- composition through the public `TacClawGripper` API, with no direct vendor import

The DataMaster trigger-to-gripper-position mapping is deliberately not migrated here. It is a teleoperation policy and belongs in `teleop_retarget`.

Source snapshot provenance is recorded by `datamaster_wrapper/docs/migration/source_manifest.sha256`; the legacy `tacclaw.py` checksum is `cb5622742d8dbd25c0c498cb542914b2fefaf323827d6a2380c7dd390d25010d`.
