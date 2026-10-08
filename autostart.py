"""Start background renaming when the computer starts, so nobody has to add it to
the start-up apps by hand. On Windows: a shortcut in the user's Startup folder,
which Windows runs at sign-in (no administrator rights needed). On a Mac: a login
item (a LaunchAgent in ~/Library/LaunchAgents). Elsewhere these do nothing.

Started this way, background renaming waits the start-up wait first, so Google
Drive can bring new files down. Started from the window (`--now`), it doesn't."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import notify

NAME = "Smart Explorer (background).lnk"  # packaging/windows-installer.iss removes this name on uninstall
MAC_LABEL = "com.jimhoggey.smartexplorer.watch"
SCRIPT = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SE_LNK); "
          "$s.TargetPath = $env:SE_TARGET; $s.Arguments = $env:SE_ARGS; "
          "$s.WorkingDirectory = $env:SE_DIR; $s.Save()")


def available(system=None):
    return (system or sys.platform) in ("win32", "darwin")


def shortcut():
    """Where the start-up entry lives: the Windows shortcut, or the Mac login item."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / (MAC_LABEL + ".plist")
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / NAME


def watch_command(now=False):
    """argv that starts background renaming: the installed app, or from source the
    same Python (pythonw on Windows, so no console window opens). now: skip the
    start-up wait, for a start from the window rather than the computer starting."""
    if getattr(sys, "frozen", False):
        argv = [sys.executable, "--watch"]
    else:
        exe = Path(sys.executable)
        windowless = exe.with_name("pythonw.exe")
        argv = [str(windowless if windowless.exists() else exe), str(Path(__file__).resolve().parent / "desktop.py"), "--watch"]
    return argv + ["--now"] if now else argv


def enabled():
    return available() and shortcut().exists()


def enable(run=subprocess.run):
    """Create (or refresh) the start-up entry. Returns None, or why it failed."""
    if not available():
        return "Starting with the computer is only available on Windows and Mac."
    argv = watch_command()
    why = "Could not add Smart Explorer to the computer's start-up: %s"
    if sys.platform == "darwin":
        try:
            shortcut().parent.mkdir(parents=True, exist_ok=True)
            shortcut().write_bytes(plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": argv, "RunAtLoad": True}))
        except OSError as e:
            return why % e
        return None
    shortcut().parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SE_LNK=str(shortcut()), SE_TARGET=argv[0], SE_ARGS=subprocess.list2cmdline(argv[1:]),
               SE_DIR=str(Path(argv[0]).parent))
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
