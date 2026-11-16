# AirLift core (vendored)

This directory is a vendored copy of the AirLift (ATAirlock) file-write
driver, integrated into Nugget as an additional delivery backend next to
SparseRestore and BookRestore.

## Provenance

- Core code: [PyAirLift](https://github.com/awesomenull-dev/PyAirLift)
  (`src/airlift/__init__.py` and `src/airlift/grappa.py`), commit
  `c840a2c3e9bc649030102c046ab75d66da556654`, version 0.1.0, MIT license.
  PyAirLift is a cross-platform (Linux / Windows / macOS) Python port of
  the AirLift implementation in GoldenNugget.
- Original research / exploit: [airlift](https://github.com/0xjohnnydev/airlift)
  by 0xjohnnydev — an AirTraffic (Apple Books sync) sandbox escape:
  `-[ATAirlock processCompletedAsset:]` follows a staged symlink out of
  `/var/mobile/Media`, so a paired host can place **new** files in
  sandbox-external directories (e.g. `/var/mobile/Library/Caches`,
  `/var/mobile/Library/SpringBoard`, app containers, `/var/tmp`).

## Local modifications

Kept minimal so the core can be re-synced from PyAirLift:

1. Logger names changed from `GoldenNugget.airlift*` to `Nugget.airlift*`.
2. The ATC `HostInfo` `MacOSVersion` string is `"Nugget"`.
3. The Grappa-token debug override accepts `NUGGET_ATC_GRAPPA` in addition
   to the upstream `GOLDENNUGGET_ATC_GRAPPA` environment variable.

## Hard limits of this backend (by design of the exploit)

- **New files only.** ATAirlock moves files with a rename, so a file whose
  name already exists on the device cannot be overwritten. Re-applying the
  same files is reported as failures, not as an error of the whole apply.
- **No MobileGestalt.** There is no working AirLift path to the
  MobileGestalt plist, so gestalt/AI tweaks are *not* offered over AirLift.
- **iPhone only**, device must be unlocked and trust this computer.
- **Patched in iOS 27.2 beta 3 (24B5099f) and later 27.2+ builds.**
  Verified upstream builds are listed in `TESTED_BUILDS`; other builds are
  warned about but not blocked by the core.
