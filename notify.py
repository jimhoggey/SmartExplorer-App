"""Desktop notifications for background renaming: a Windows toast, or a Mac
notification. Showing one must never stop the renaming, so notify() never raises."""
import base64
import os
import subprocess
import sys
from xml.sax.saxutils import escape

TITLE = "Smart Explorer"
APP_ID = "jimhoggey.SmartExplorer"  # the installer puts this on the Start menu shortcut
# Run from source there is no such shortcut; Windows then shows the toast as PowerShell's.
POWERSHELL_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
TOAST = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:SE_TOAST)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:SE_APP_ID).Show($toast)
"""
MAC = ["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
       "-e", "end run"]


def powershell(script):
    """argv that runs a PowerShell script without quoting trouble."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode()]


def command(title, text, system=None, frozen=None):
    """(argv, extra environment) that shows the notification, or None where there is no way."""
    system = system or sys.platform
    if system == "win32":
        installed = getattr(sys, "frozen", False) if frozen is None else frozen
        xml = ('<toast><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text>'
               "</binding></visual></toast>") % (escape(title), escape(text))
        return powershell(TOAST), {"SE_TOAST": xml, "SE_APP_ID": APP_ID if installed else POWERSHELL_ID}
    if system == "darwin":
        return MAC + [title, text], {}
    return None


def notify(text, title=TITLE, run=subprocess.run):
    """Show a notification. Returns None when it was shown, else why not (for the log)."""
    cmd = command(title, text)
    if not cmd:
        return "notifications are not available on this computer"
    argv, env = cmd
    kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}
    try:
        r = run(argv, env=dict(os.environ, **env), capture_output=True, timeout=30, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    if r.returncode == 0:
        return None
    return (r.stderr or b"").decode(errors="replace").strip()[:300] or "exit code %d" % r.returncode
