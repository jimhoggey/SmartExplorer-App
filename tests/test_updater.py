import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import config
import updater


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(updater, "_cache", {"at": 0.0, "info": None, "asset": None})
    monkeypatch.setattr(updater, "STATE", {"state": "idle", "done": 0, "total": 0, "error": None})


def release(tag="v9.9.9", digest=True):
    name = "SmartExplorer-%s-windows-setup.exe" % tag.lstrip("v")
    asset = {"name": name, "size": 4, "browser_download_url": "https://example.test/" + name}
    if digest:
        asset["digest"] = "sha256:" + hashlib.sha256(b"data").hexdigest()
    return {"tag_name": tag, "html_url": "https://github.com/x/releases/tag/" + tag, "assets": [asset]}


@pytest.fixture
def github(monkeypatch, tmp_path):
    """GitHub answering with a release; this copy installed on Windows."""
    calls = []

    def serve(body):
        def fake(req, timeout=None):
            calls.append(req.full_url)
            return io.BytesIO(json.dumps(body).encode())
        monkeypatch.setattr(updater, "urlopen", fake)

    monkeypatch.setattr(updater, "asset_name", lambda v: "SmartExplorer-%s-windows-setup.exe" % v)
    monkeypatch.setattr(updater, "installed_app", lambda: (tmp_path, None))
    serve(release())
    return serve, calls


def test_versions_compare_as_numbers():
    assert updater.parse("v0.3.0") == (0, 3, 0) and updater.parse("0.10.2") == (0, 10, 2)
    assert updater.parse("v1.0.0-beta") is None and updater.parse("") is None
    assert updater.newer("0.10.0", "0.9.9") and updater.newer("v1.0.0", "0.3.0")
    assert not updater.newer("0.3.0", "0.3.0") and not updater.newer("0.2.9", "0.3.0")
    assert not updater.newer("v1.0.0-beta", "0.3.0")


def test_each_computer_gets_its_own_installer():
    assert updater.asset_name("0.4.0", "darwin", "arm64") == "SmartExplorer-0.4.0-mac-apple-silicon.dmg"
    assert updater.asset_name("0.4.0", "darwin", "x86_64") == "SmartExplorer-0.4.0-mac-intel.dmg"
    assert updater.asset_name("0.4.0", "win32", "AMD64") == "SmartExplorer-0.4.0-windows-setup.exe"
    assert updater.asset_name("0.4.0", "linux", "x86_64") is None


def test_where_the_app_is_installed(tmp_path, monkeypatch):
    exe = tmp_path / "Smart Explorer.app" / "Contents" / "MacOS" / "Smart Explorer"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert updater.installed_app(frozen=False)[0] is None  # from source: git pull instead
    assert updater.installed_app(True, str(exe), "darwin") == (tmp_path / "Smart Explorer.app", None)
    assert updater.installed_app(True, str(tmp_path / "Smart Explorer.exe"), "win32") == (tmp_path, None)
    moved = "/private/var/folders/x/AppTranslocation/ABC/d/Smart Explorer.app/Contents/MacOS/Smart Explorer"
    assert "Applications" in updater.installed_app(True, moved, "darwin")[1]
    assert updater.installed_app(True, "/Volumes/Smart Explorer/Smart Explorer.app/Contents/MacOS/x", "darwin")[0] is None
    monkeypatch.setattr(updater.os, "access", lambda p, mode: False)
    assert "cannot replace" in updater.installed_app(True, str(exe), "darwin")[1]
    assert updater.installed_app(True, "/usr/bin/smart-explorer", "linux")[0] is None


def test_check_finds_a_newer_release_and_reuses_the_answer(github):
    serve, calls = github
    info = updater.check()
    assert info["newer"] and info["can_install"] and info["latest"] == "9.9.9" and info["size"] == 4
    assert info["current"] == updater.APP_VERSION and info["page"].endswith("v9.9.9")
    updater.check()
    assert len(calls) == 1  # asked GitHub once
    updater.check(force=True)
    assert len(calls) == 2


def test_check_same_version_or_unverifiable_installer(github):
    serve, calls = github
    serve(release("v" + updater.APP_VERSION))
    assert not updater.check(force=True)["newer"]
    serve(release(digest=False))
    info = updater.check(force=True)
    assert info["newer"] and not info["can_install"] and "checksum" in info["why_not"]


def test_check_offline(monkeypatch):
    def down(req, timeout=None):
        raise OSError("no network")
    monkeypatch.setattr(updater, "urlopen", down)
    info = updater.check()
    assert "Could not check" in info["error"] and "newer" not in info


def test_a_failed_update_is_noticed(github):
    config.save(update_attempt="9.9.9")
    assert updater.check(force=True)["failed"] == "9.9.9"
    config.save(update_attempt=updater.APP_VERSION)  # it worked: this is that version
    assert "failed" not in updater.check(force=True)


def test_download_checks_size_and_sha256(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "urlopen", lambda req, timeout=None: io.BytesIO(b"data"))
    asset = release()["assets"][0]
    seen = []
    path = updater.download(asset, tmp_path, lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == b"data" and seen[-1] == (4, 4)
    with pytest.raises(updater.UpdateError):
        updater.download(dict(asset, digest="sha256:" + "0" * 64), tmp_path)
    with pytest.raises(updater.UpdateError):
        updater.download(dict(asset, size=5), tmp_path)  # cut short
    assert not (tmp_path / asset["name"]).exists()  # a bad download is not left behind


def test_launch_runs_the_installer_detached(tmp_path):
    started = []
    popen = lambda args, **kw: started.append((args, kw))
    dmg = tmp_path / "SmartExplorer-9.9.9-mac-apple-silicon.dmg"
    updater.launch(dmg, Path("/Applications/Smart Explorer.app"), "darwin", popen)
    args, kw = started[0]
    assert args[:2] == ["/bin/sh", str(tmp_path / "update.sh")] and args[3:] == [str(dmg), "/Applications/Smart Explorer.app"]
    assert (tmp_path / "update.sh").read_text() == updater.MAC_SCRIPT and kw["start_new_session"]
    exe = tmp_path / "SmartExplorer-9.9.9-windows-setup.exe"
    updater.launch(exe, tmp_path, "win32", popen)
    args, kw = started[1]
    assert args[0] == str(exe) and {"/SILENT", "/CURRENTUSER", "/RELAUNCH=1", "/SUPPRESSMSGBOXES"} <= set(args)


def test_start_downloads_installs_and_closes(github, monkeypatch, tmp_path):
    assert "Check for updates" in updater.start()  # nothing found yet
    updater.check()
    done = []
    monkeypatch.setattr(updater, "download", lambda asset, folder, progress: progress(4, 4) or tmp_path / asset["name"])
    monkeypatch.setattr(updater, "launch", lambda installer, app: done.append(("launch", installer.name, app)))
    monkeypatch.setattr(updater, "quit_app", lambda: done.append(("quit",)))
    assert updater.start() is None
    for _ in range(40):
        if ("quit",) in done:
            break
        time.sleep(0.1)
    assert done == [("launch", "SmartExplorer-9.9.9-windows-setup.exe", tmp_path), ("quit",)]
    assert updater.STATE["state"] == "restarting" and updater.STATE["done"] == 4
    assert config.load()["update_attempt"] == "9.9.9"


def test_start_reports_a_failed_download(github, monkeypatch):
    updater.check()

    def broken(asset, folder, progress):
        raise updater.UpdateError("The download did not match")
    monkeypatch.setattr(updater, "download", broken)
    updater.start()
    for _ in range(40):
        if updater.STATE["state"] == "error":
            break
        time.sleep(0.05)
    assert updater.STATE["error"] == "The download did not match"


# The Mac swap script, run for real with stand-ins for hdiutil, ditto and open.
@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX shell")
@pytest.mark.parametrize("copy_works", [True, False])
def test_mac_script_swaps_the_app_or_keeps_the_old_one(tmp_path, copy_works):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "calls"
    (bin_ / "hdiutil").write_text(
        '#!/bin/sh\necho "hdiutil $1" >> %s\n'
        'if [ "$1" = attach ]; then eval "mnt=\\${$(($# - 1))}" ; eval "src=\\${$#}"; cp -R "$src/." "$mnt"; fi\n' % log)
    (bin_ / "ditto").write_text("#!/bin/sh\n%s\n" % ('cp -R "$1" "$2"' if copy_works else "exit 1"))
    (bin_ / "open").write_text('#!/bin/sh\necho "open $1" >> %s\n' % log)
    for f in bin_.iterdir():
        f.chmod(0o755)
    dmg = tmp_path / "dmg"  # stands in for the mounted image's contents
    (dmg / "Smart Explorer.app").mkdir(parents=True)
    (dmg / "Smart Explorer.app" / "version").write_text("new")
    app = tmp_path / "Applications" / "Smart Explorer.app"
    app.mkdir(parents=True)
    (app / "version").write_text("old")
    script = tmp_path / "update.sh"
    script.write_text(updater.MAC_SCRIPT)
    gone = subprocess.Popen(["true"])
    gone.wait()
    out = subprocess.run(["/bin/sh", str(script), str(gone.pid), str(dmg), str(app)], capture_output=True, text=True,
                         env=dict(os.environ, PATH="%s:%s" % (bin_, os.environ["PATH"]), TMPDIR=str(tmp_path)), timeout=60)
    assert (app / "version").read_text() == ("new" if copy_works else "old")
    assert not (app.parent / "Smart Explorer.app.new").exists() and not (app.parent / "Smart Explorer.app.old").exists()
    assert ("updated" if copy_works else "could not replace") in out.stdout
    assert log.read_text().splitlines()[-1] == "open %s" % app  # the app opens again either way
