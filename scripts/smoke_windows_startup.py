"""Windows only, run by CI on the built app: prove "Start by itself when the computer
starts" really works, not just that a setting was saved.

With the app running windowless, it turns watching on with start-up ticked through
the same /api/watch the Settings window uses, then checks that:
1. the app reads back that it is in the start-up items;
2. the shortcut is in the Startup folder and points at the app with --watch;
3. starting that shortcut the way Windows does at sign-in starts background
   renaming, which renames new files;
4. turning watching off removes the shortcut;
and that the Google Drive check can read the running programs.

    python scripts/smoke_windows_startup.py "dist/Smart Explorer/Smart Explorer.exe"
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import autostart  # noqa: E402
import drive  # noqa: E402
import notify  # noqa: E402

PORT = 8768
URL = "http://127.0.0.1:%d/api/" % PORT


def api(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def until(what, check, seconds):
    for _ in range(seconds):
        if check():
            print("ok:", what, flush=True)
            return
        time.sleep(1)
    raise SystemExit("FAILED: " + what)


def shortcut_fields(lnk):
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SE_LNK); "
              "Write-Output $s.TargetPath; Write-Output $s.Arguments")
    out = subprocess.run(notify.powershell(script), env=dict(os.environ, SE_LNK=str(lnk)),
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return [line.strip() for line in out if line.strip()]


def main(exe):
    if sys.platform != "win32":
        raise SystemExit("Windows only")
    exe = str(Path(exe).resolve())
    os.environ["SMART_EXPLORER_MOCK"] = "1"  # names files "Slide N" without a key; inherited by what this starts
    app = subprocess.Popen([exe], env=dict(os.environ, SMART_EXPLORER_HEADLESS="1", SMART_EXPLORER_PORT=str(PORT)))
    try:
        until("the app answers", lambda: _answers(), 90)
        folder = Path(tempfile.mkdtemp(prefix="se-startup-")) / "Sunday Media"
        folder.mkdir()

        w = api("watch", {"enabled": True, "folder": str(folder), "startup_wait_min": 0, "autostart": True})
        if w.get("error") or not w.get("autostart_on"):
            raise SystemExit("FAILED: the app did not add itself to the start-up items: %s" % w)
        print("ok: the app reads back that it is in the start-up items", flush=True)

        lnk = autostart.shortcut()
        fields = shortcut_fields(lnk)
        print("shortcut:", lnk, fields, flush=True)
        if not lnk.exists() or len(fields) < 2 or Path(fields[0]).resolve() != Path(exe) or fields[1] != "--watch":
            raise SystemExit("FAILED: the Startup shortcut is missing or wrong")
        print("ok: the Startup shortcut points at the app with --watch", flush=True)

        # Stop the copy the app started, so the next one can only come from the shortcut.
        stop = Path.home() / ".smart-explorer" / "watch" / "stop"
        stop.write_text("stop")
        until("the app's own background copy stopped", lambda: not api("watch")["running"], 60)

        os.startfile(str(lnk))  # what Windows does with each Startup shortcut at sign-in
        until("the shortcut started background renaming", lambda: api("watch")["running"], 60)
        for n, colour in (("1.png", "red"), ("2.png", "blue")):
            Image.new("RGB", (64 + len(colour), 36), colour).save(folder / n)
        until("new files renamed by the copy the shortcut started",
              lambda: sorted(p.name for p in folder.iterdir()) == ["01 Slide 1.png", "02 Slide 2.png"], 180)

        w = api("watch", {"enabled": False})
        until("turning watching off removed the shortcut", lambda: not lnk.exists() and not api("watch")["autostart_on"], 30)
        until("background renaming stopped", lambda: not api("watch")["running"], 60)

        up = drive.running()
        print("Google Drive running on this computer:", up, flush=True)
        if up is None:
            raise SystemExit("FAILED: the Google Drive check could not read the running programs")
        print("notification:", notify.notify("Smart Explorer CI check") or "shown", flush=True)
        print("all start-up checks passed")
        return 0
    finally:
        app.kill()


def _answers():
    try:
        api("status")
        return True
    except OSError:
        return False


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
