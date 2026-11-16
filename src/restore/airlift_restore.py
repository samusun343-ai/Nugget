"""AirLift delivery backend for Nugget.

Routes ``FileToRestore`` objects through the AirLift (ATAirlock) driver in
``src.airlift`` instead of a backup restore. AirLift is the only delivery
method left on iOS versions where both SparseRestore and BookRestore are
patched (iOS 26.2+ / 27.x), and it needs no reboot.

Eligibility is deliberately narrow - AirLift can only:

- create **new** files (ATAirlock renames; existing files cannot be
  overwritten, they are reported back as failures), and
- reach the directories that were verified for fresh-file writes
  (``AIRLIFT_REACHABLE_ROOTS`` below, from the upstream research).

Files that do not qualify (anything with a restore domain, plist merges in
system domains, MobileGestalt, ...) must keep using the restore backends.
"""
import os
import posixpath

from pymobiledevice3.lockdown import LockdownClient

from .restore import FileToRestore
from src.airlift import AirliftError, check_target, write_files

# Directories where fresh-file AirLift writes were verified upstream
# (0xjohnnydev/airlift, iOS 27.0 RC) plus the TelephonyUI cache folders
# that AirCard/GoldenNugget write passcode themes into.
AIRLIFT_REACHABLE_ROOTS: tuple[str, ...] = (
    "/var/mobile/Documents",
    "/var/mobile/Library/Preferences",
    "/var/mobile/Library/Caches",
    "/var/mobile/Library/SpringBoard",
    "/var/mobile/Library/SMS",
    "/var/mobile/Library/Safari",
    "/var/mobile/Library",
    "/var/mobile/Containers/Data/Application",
    "/var/mobile/Containers/Shared/AppGroup",
    "/var/mobile/Containers",
    "/var/mobile",
    "/var/tmp",
)


def is_airlift_eligible(file: FileToRestore) -> bool:
    """Whether a single file can be delivered over AirLift."""
    # domain-based files belong to the backup-restore domains; AirLift
    # writes by absolute on-device path only.
    if file.domain not in (None, ""):
        return False
    path = file.restore_path
    if not path.startswith("/"):
        return False
    dir_path = posixpath.dirname(posixpath.normpath(path))
    return any(
        dir_path == root or dir_path.startswith(root + "/")
        for root in AIRLIFT_REACHABLE_ROOTS
    )


def partition_airlift_files(
    files: list[FileToRestore],
) -> tuple[list[FileToRestore], list[FileToRestore]]:
    """Split files into (airlift-eligible, restore-only) lists."""
    eligible: list[FileToRestore] = []
    rest: list[FileToRestore] = []
    for file in files:
        (eligible if is_airlift_eligible(file) else rest).append(file)
    return eligible, rest


def has_airlift_capability(lockdown_client: LockdownClient = None) -> bool:
    """Device-side gate, mirroring ``has_sparserestore_capability``.

    The AirLift core raises on non-iPhone / unpaired devices; builds that
    are not in its verified set are warned about but still allowed.
    """
    if lockdown_client is None:
        return True
    try:
        check_target(lockdown_client)
        return True
    except AirliftError:
        return False


def _file_contents(file: FileToRestore) -> bytes:
    if file.contents is not None:
        return file.contents
    if file.contents_path is not None:
        with open(file.contents_path, "rb") as fh:
            return fh.read()
    return b""


async def restore_files_via_airlift(
    files: list[FileToRestore],
    lockdown_client: LockdownClient = None,
    progress_callback=lambda x: None,
) -> dict:
    """Write files to the device over AirLift, grouped by directory.

    Returns ``{"written": [...paths...], "failures": [...paths...]}``.
    Raises ``AirliftError`` when nothing could be written at all, so the
    caller can surface a real failure instead of a false success.
    """
    eligible, ineligible = partition_airlift_files(files)
    if ineligible:
        names = ", ".join(f.restore_path for f in ineligible)
        print(f"airlift: skipping files outside the reachable roots: {names}")
    if not eligible:
        raise AirliftError("no AirLift-eligible files to write")
    if lockdown_client is None:
        raise AirliftError("AirLift requires a lockdown client")

    check_target(lockdown_client, log_cb=lambda msg: print(msg))

    # group by target directory: one AirTraffic session per directory
    groups: dict[str, list[tuple[str, bytes, str]]] = {}
    for file in eligible:
        norm = posixpath.normpath(file.restore_path)
        groups.setdefault(posixpath.dirname(norm), []).append(
            (posixpath.basename(norm), _file_contents(file), file.restore_path)
        )

    written: list[str] = []
    failures: list[str] = []
    total = len(eligible)
    done = 0
    for target_dir, entries in groups.items():
        payloads = [(leaf, data) for leaf, data, _ in entries]
        result = await write_files(
            lockdown_client, target_dir, payloads,
            log_cb=lambda msg: print(msg),
        )
        written_names = set(result.get("written", []))
        for leaf, _, full_path in entries:
            (written if leaf in written_names else failures).append(full_path)
            done += 1
            progress_callback(done * 100.0 / total)

    if not written:
        raise AirliftError(
            "AirLift could not write any file. If the files already exist "
            "on the device this is expected: AirLift can only create new "
            f"files. Failed: {', '.join(failures)}"
        )
    return {"written": written, "failures": failures}
