"""Start background renaming when Windows starts: a shortcut in the user's Startup
folder, which Windows runs at sign-in. No administrator rights needed. On other
systems these do nothing."""
import os
import subprocess
import sys
from pathlib import Path

import notify

NAME = "Smart Explorer (background).lnk"  # packaging/windows-installer.iss removes this name on uninstall
SCRIPT = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SE_LNK); "
          "$s.TargetPath = $env:SE_TARGET; $s.Arguments = $env:SE_ARGS; "
          "$s.WorkingDirectory = $env:SE_DIR; $s.Save()")


def available(system=None):
    return (system or sys.platform) == "win32"


def shortcut():
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / NAME


def watch_command():
    """argv that starts background renaming: the installed app, or from source the
    same Python (pythonw on Windows, so no console window opens)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--watch"]
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return [str(windowless if windowless.exists() else exe), str(Path(__file__).resolve().parent / "desktop.py"), "--watch"]


def enabled():
    return available() and shortcut().exists()


def enable(run=subprocess.run):
    """Create (or refresh) the Startup shortcut. Returns None, or why it failed."""
    if not available():
        return "Starting with the computer is only available on Windows."
    argv = watch_command()
    shortcut().parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SE_LNK=str(shortcut()), SE_TARGET=argv[0], SE_ARGS=subprocess.list2cmdline(argv[1:]),
               SE_DIR=str(Path(argv[0]).parent))
    why = "Could not add Smart Explorer to Windows start-up: %s"
    try:
        r = run(notify.powershell(SCRIPT), env=env, capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return why % e
    if r.returncode != 0:
        return why % ((r.stderr or b"").decode(errors="replace").strip()[:300] or "exit code %d" % r.returncode)
    return None


def disable():
    if available():
        try:
            shortcut().unlink()
        except FileNotFoundError:
            pass
