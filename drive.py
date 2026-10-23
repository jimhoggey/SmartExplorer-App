"""Is Google Drive for desktop running? Background renaming only sees the files
Drive brings down, so when the watched folder is a Drive folder and Drive isn't
running, it says so instead of quietly reporting "no new files".

This looks at the running programs, the way Task Manager or Activity Monitor
does: GoogleDriveFS.exe on Windows, "Google Drive" on a Mac. It can tell whether
Drive runs, not how far its sync has got: Drive offers no way to ask that.
"""
import re
import subprocess
import sys

WINDOWS_PROGRAM = "GoogleDriveFS.exe"
MAC_PROGRAM = "Google Drive"
FOLDERS = {"my drive", "shared drives", "google drive"}  # folder names Drive gives its folders


def is_drive_folder(path):
    """Whether a folder is inside Google Drive: G:\\My Drive\\…, C:\\Users\\…\\My Drive\\…,
    …/CloudStorage/GoogleDrive-name@example.com/…, or a Shared drive."""
    parts = [p.lower() for p in re.split(r"[\\/]", str(path or "")) if p]
    return any(p in FOLDERS or p.startswith("googledrive-") for p in parts)


def running(run=subprocess.run, system=None):
    """True or False, or None when this computer can't tell (then nothing is said)."""
    system = system or sys.platform
    try:
        if system == "win32":
            r = run(["tasklist", "/FI", "IMAGENAME eq " + WINDOWS_PROGRAM, "/NH", "/FO", "CSV"], capture_output=True,
                    timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                return None
            return WINDOWS_PROGRAM.lower().encode() in (r.stdout or b"").lower()
        if system == "darwin":
            r = run(["pgrep", "-x", MAC_PROGRAM], capture_output=True, timeout=15)
            return {0: True, 1: False}.get(r.returncode)
    except (OSError, subprocess.SubprocessError):
        return None
    return None
