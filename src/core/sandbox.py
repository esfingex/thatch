"""Zeus Sandbox Isolation — single source of truth for prefix lockdown.

Previously the sandbox contract lived in three places (the generated launcher
bash block, zeus_dialog's post-install re-lock and assorted inline logic), each
with its own assumptions. This module unifies them so the guarantee — no z:
drive to /, no user-folder symlinks leaking the host home — is enforced by one
mechanism with one behavior, testable in isolation.
"""

from pathlib import Path

SANDBOXED_USER_FOLDERS = [
    "Desktop",
    "Documents",
    "Downloads",
    "Music",
    "Pictures",
    "Videos",
]

_FALLBACK_WIN_USER = "steamuser"


def detect_prefix_user(prefix_path: Path) -> str:
    """Returns the Windows username actually present in the prefix.

    The old contract hardcoded 'steamuser', which silently disabled the sandbox
    for prefixes created with a different user. Public/Default are excluded.
    """
    users_dir = Path(prefix_path) / "drive_c" / "users"
    if users_dir.is_dir():
        for entry in users_dir.iterdir():
            if entry.is_dir() and entry.name.lower() not in (
                "public",
                "default",
                "all users",
            ):
                return entry.name
    return _FALLBACK_WIN_USER


def enforce_sandbox(prefix_path: Path) -> int:
    """Applies the sandbox contract to a prefix, idempotently.

    - Removes the 'z:' dosdevice symlink to / (only symlinks; a real z: dir is
      left untouched rather than deleted).
    - Replaces user-folder symlinks (Desktop, Documents, ...) with clean local
      directories, matching the original bash contract semantics.

    Returns the number of host-facing links removed.
    """
    prefix_path = Path(prefix_path)
    removed = 0

    z_drive = prefix_path / "dosdevices" / "z:"
    if z_drive.is_symlink():
        try:
            z_drive.unlink()
            removed += 1
        except OSError as e:
            print(f"[Sandbox] Failed to remove z: drive in {prefix_path.name}: {e}")

    user_dir = prefix_path / "drive_c" / "users" / detect_prefix_user(prefix_path)
    if user_dir.is_dir():
        for folder in SANDBOXED_USER_FOLDERS:
            link = user_dir / folder
            if link.is_symlink():
                try:
                    link.unlink()
                    removed += 1
                except OSError as e:
                    print(f"[Sandbox] Failed to unlink {folder} in {prefix_path.name}: {e}")
            if not link.exists():
                try:
                    link.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    print(f"[Sandbox] Failed to recreate {folder} in {prefix_path.name}: {e}")

    return removed


def is_sandboxed(prefix_path: Path) -> bool:
    """True if the prefix currently exposes the z: drive or user-folder symlinks."""
    prefix_path = Path(prefix_path)
    z_drive = prefix_path / "dosdevices" / "z:"
    if z_drive.is_symlink():
        return False

    user_dir = prefix_path / "drive_c" / "users" / detect_prefix_user(prefix_path)
    if user_dir.is_dir():
        for folder in SANDBOXED_USER_FOLDERS:
            if (user_dir / folder).is_symlink():
                return False
    return True
