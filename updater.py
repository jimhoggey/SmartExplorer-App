"""Keeps the installed app up to date from GitHub releases.

When the window opens it asks GitHub for the latest release. If that is newer,
the window offers to update. "Update now" downloads this computer's installer
from the release, checks it against the size and SHA-256 that GitHub lists for
it, runs it, and closes the app; the new version opens in its place.
- Mac: a small script waits for the app to quit, copies the new app out of the
  .dmg next to the old one, swaps the two, and opens it. If anything fails, the
  old app stays where it was.
- Windows: the installer runs over the old install with a progress bar and no
  questions, then opens the app (/RELAUNCH=1).
Run from source there is nothing to replace, so the window links to the release.
"""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request

import config
from net import urlopen
from version import APP_VERSION

REPO = "jimhoggey/SmartExplorer-App"
LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
PAGE = "https://github.com/%s/releases/latest" % REPO
CHECK_EVERY = 6 * 3600  # seconds a check's answer is reused
HEADERS = {"User-Agent": "Smart-Explorer/" + APP_VERSION, "Accept": "application/vnd.github+json"}

LOCK = threading.Lock()
_cache = {"at": 0.0, "info": None, "asset": None}
STATE = {"state": "idle", "done": 0, "total": 0, "error": None}  # idle, downloading, installing, restarting, error


class UpdateError(Exception):
    pass


def parse(version):
    """(0, 3, 0) from "v0.3.0" or "0.3.0"; None for anything else (a beta, a typo)."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    return tuple(int(n) for n in m.groups()) if m else None


def newer(latest, current=APP_VERSION):
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


def asset_name(version, system=sys.platform, machine=platform.machine()):
    """The release file for this computer, as the build names it."""
    if system == "darwin":
        return "SmartExplorer-%s-mac-%s.dmg" % (version, "apple-silicon" if machine == "arm64" else "intel")
    if system == "win32":
        return "SmartExplorer-%s-windows-setup.exe" % version
    return None


def installed_app(frozen=None, executable=None, system=None):
    """(where this copy is installed, None) or (None, why it cannot replace itself)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    exe = Path(executable or sys.executable).resolve()
    system = system or sys.platform
    if not frozen:
        return None, "This copy runs from source; update it with git pull."
    if system == "darwin":
        app = exe.parents[2]  # Smart Explorer.app/Contents/MacOS/Smart Explorer
        if app.suffix != ".app":
            return None, "Could not find the app to replace."
        if "/AppTranslocation/" in str(app) or str(app).startswith("/Volumes/"):
            return None, "Move Smart Explorer to Applications, open it from there, then update."
        if not os.access(app.parent, os.W_OK):
            return None, "This Mac account cannot replace apps in %s." % app.parent
        return app, None
    if system == "win32":
        return exe.parent, None
    return None, "There is no installer for this system."


def check(force=False):
    """What the window shows: this version, the latest one, and whether it can install itself."""
    with LOCK:
        if not force and _cache["info"] and time.time() - _cache["at"] < CHECK_EVERY:
            return _cache["info"]
    info = {"current": APP_VERSION, "page": PAGE}
    attempted = config.load().get("update_attempt")
    if attempted and newer(attempted):
        info["failed"] = attempted  # an update was started but this is still the old version
    try:
        with urlopen(Request(LATEST, headers=HEADERS), timeout=10) as r:
            release = json.loads(r.read().decode())
    except Exception as e:
        return dict(info, error="Could not check for updates (%s)." % e)
    latest = str(release.get("tag_name") or "").lstrip("v")
    want = asset_name(latest)
    asset = next((a for a in release.get("assets") or [] if a.get("name") == want), None)
    app, why = installed_app()
    if asset and not str(asset.get("digest") or "").startswith("sha256:"):
        asset, why = None, "The release does not list a checksum for its installer."
    elif not asset and not why:
        why = "The release has no installer for this computer yet."
    info.update(latest=latest, newer=newer(latest), page=release.get("html_url") or PAGE,
                can_install=bool(asset and app), why_not=None if asset and app else why,
                size=asset.get("size") if asset else None)
    with LOCK:
        _cache.update(at=time.time(), info=info, asset=asset)
    return info


def download(asset, folder, progress=lambda done, total: None):
    """Fetch a release file and prove it is the one GitHub lists: same size, same SHA-256."""
    path = Path(folder) / asset["name"]
    total, digest = int(asset["size"]), hashlib.sha256()
    done = 0
    with urlopen(Request(asset["browser_download_url"], headers={"User-Agent": HEADERS["User-Agent"]}), timeout=60) as r, \
            open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            progress(done, total)
    if done != total or "sha256:" + digest.hexdigest() != asset["digest"]:
        path.unlink()
        raise UpdateError("The download did not match the release (it may have been cut short). Try again.")
    return path


# Run by /bin/sh after the app hands over: $1 app's process id, $2 the .dmg, $3 the
# installed .app, $4 --no-open (for tests). Prints what it did.
MAC_SCRIPT = r"""#!/bin/sh
pid=$1 dmg=$2 app=$3
n=0
while kill -0 "$pid" 2>/dev/null && [ $n -lt 120 ]; do sleep 0.5; n=$((n + 1)); done
mnt=$(mktemp -d "${TMPDIR:-/tmp}/smart-explorer-update.XXXXXX") || exit 1
if hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$mnt" "$dmg"; then
  rm -rf "$app.new" "$app.old"
  if ditto "$mnt/Smart Explorer.app" "$app.new" && mv "$app" "$app.old" && mv "$app.new" "$app"; then
    rm -rf "$app.old"
    echo "updated $app"
  else
    [ -d "$app" ] || mv "$app.old" "$app"
    rm -rf "$app.new"
    echo "could not replace $app; the old version is still there"
  fi
  hdiutil detach -quiet "$mnt" || hdiutil detach -force -quiet "$mnt"
else
  echo "could not open $dmg"
fi
rmdir "$mnt" 2>/dev/null
rm -f "$dmg"
[ "$4" = "--no-open" ] || open "$app"
"""


def launch(installer, app, system=None, popen=subprocess.Popen):
    """Start the installer so that it outlives this app."""
    system = system or sys.platform
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(config.CONFIG_DIR / "update.log", "a")
    if system == "darwin":
        script = Path(installer).parent / "update.sh"
        script.write_text(MAC_SCRIPT)
        popen(["/bin/sh", str(script), str(os.getpid()), str(installer), str(app)],
              stdout=log, stderr=log, start_new_session=True)
    else:
        # Per-user installs (the default) update silently; an install in Program
        # Files needs an administrator, so Windows asks for one.
        who = "/CURRENTUSER" if os.access(app, os.W_OK) else "/ALLUSERS"
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen([str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", who, "/RELAUNCH=1"],
              stdout=log, stderr=log, creationflags=flags, close_fds=True)


def quit_app():
    """Close the window so the installer can replace the app; exit anyway after 3 s."""
    try:
        import webview
        for w in list(webview.windows):
            w.destroy()
    except Exception:
        pass
    t = threading.Timer(3.0, lambda: os._exit(0))
    t.daemon = True
    t.start()


def start():
    """Begin updating in the background; the window polls STATE. Returns an error message or None."""
    with LOCK:
        info, asset = _cache["info"], _cache["asset"]
        if STATE["state"] in ("downloading", "installing", "restarting"):
            return None
        if not (info and info.get("newer") and info.get("can_install") and asset):
            return "There is no update to install. Check for updates first."
        app, why = installed_app()
        if not app:
            return why
        STATE.update(state="downloading", done=0, total=int(asset["size"]), error=None)
    threading.Thread(target=_install, args=(asset, app, info["latest"]), daemon=True).start()
    return None


def _install(asset, app, version):
    def progress(done, total):
        STATE["done"] = done

    try:
        installer = download(asset, tempfile.mkdtemp(prefix="smart-explorer-update-"), progress)
        STATE["state"] = "installing"
        with LOCK:
            config.save(update_attempt=version)
        launch(installer, app)
        STATE["state"] = "restarting"
        threading.Timer(1.0, quit_app).start()  # time for the window to show "restarting"
    except Exception as e:
        STATE.update(state="error", error=str(e))
