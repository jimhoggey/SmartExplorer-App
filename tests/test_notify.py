import base64
import subprocess
import sys
from pathlib import Path

import autostart
import notify


def test_windows_toast_escapes_text_and_picks_the_app_id():
    argv, env = notify.command("Smart Explorer", "Giving & <Offering>", system="win32", frozen=True)
    assert argv[0] == "powershell" and "-EncodedCommand" in argv
    script = base64.b64decode(argv[argv.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert "ToastNotificationManager" in script and "$env:SE_TOAST" in script
    assert "Giving &amp; &lt;Offering&gt;" in env["SE_TOAST"] and env["SE_APP_ID"] == notify.APP_ID
    assert notify.command("t", "x", system="win32", frozen=False)[1]["SE_APP_ID"] == notify.POWERSHELL_ID


def test_mac_notification_passes_text_as_arguments():
    argv, env = notify.command("Smart Explorer", 'Say "hi"', system="darwin")
    assert argv[0] == "osascript" and argv[-2:] == ["Smart Explorer", 'Say "hi"'] and env == {}
    assert notify.command("t", "x", system="linux") is None


def test_notify_never_raises(monkeypatch):
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    ok = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"", b"")
    assert notify.notify("hi", run=ok) is None
    bad = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, b"", b"not allowed")
    assert notify.notify("hi", run=bad) == "not allowed"

    def boom(argv, **kw):
        raise OSError("no osascript")

    assert "no osascript" in notify.notify("hi", run=boom)
    monkeypatch.setattr(notify.sys, "platform", "linux")
    assert notify.notify("hi", run=ok)


def test_watch_command_from_source_and_installed(monkeypatch):
    argv = autostart.watch_command()
    assert argv[-2:] == [str(Path(autostart.__file__).resolve().parent / "desktop.py"), "--watch"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Apps/Smart Explorer.exe")
    assert autostart.watch_command() == ["/Apps/Smart Explorer.exe", "--watch"]


def test_autostart_on_windows_and_mac_only(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    assert not autostart.available() and not autostart.enabled()
    assert "only" in autostart.enable(run=lambda *a, **k: None)
    autostart.disable()  # nothing to do, no error
    assert autostart.available("darwin") and autostart.available("win32")


def test_watch_command_now_skips_the_wait():
    assert autostart.watch_command(now=True)[-2:] == ["--watch", "--now"]
    assert autostart.watch_command()[-1] == "--watch"


def test_mac_login_item_is_a_launch_agent(monkeypatch, tmp_path):
    import plistlib
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # where Windows (CI) finds the home folder
    calls = []
    run = lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, b"", b"")
    assert not autostart.enabled()
    assert autostart.enable(run=run) is None and autostart.enabled()
    agent = tmp_path / "Library" / "LaunchAgents" / (autostart.MAC_LABEL + ".plist")
    data = plistlib.loads(agent.read_bytes())
    assert data["Label"] == autostart.MAC_LABEL and data["RunAtLoad"] is True
    assert data["ProgramArguments"] == autostart.watch_command()  # at login: with the start-up wait
    # registered with macOS now, so it shows in Login Items without a restart
    assert [c[:2] for c in calls] == [["launchctl", "bootout"], ["launchctl", "bootstrap"]] and calls[1][-1] == str(agent)
    calls.clear()
    autostart.disable(run=run)
    assert not agent.exists() and not autostart.enabled() and calls[0][:2] == ["launchctl", "bootout"]


def test_show_opens_the_start_up_items(monkeypatch):
    seen = []
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    autostart.show(popen=lambda argv, **kw: seen.append(argv))
    assert seen[-1] == ["open", autostart.MAC_SETTINGS]
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    autostart.show(popen=lambda argv, **kw: seen.append(argv))
    assert seen[-1] == ["explorer", "shell:startup"]


def test_autostart_creates_and_removes_the_shortcut(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    seen = {}

    def run(argv, env=None, **kw):
        seen.update(env)
        Path(env["SE_LNK"]).write_bytes(b"lnk")  # what PowerShell would do
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    assert autostart.enable(run=run) is None
    assert seen["SE_LNK"].endswith(autostart.NAME) and "Startup" in seen["SE_LNK"]
    assert seen["SE_ARGS"].endswith("--watch") and autostart.enabled()
    autostart.disable()
    assert not autostart.enabled()
    fail = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, b"", b"denied")
    assert "denied" in autostart.enable(run=fail)
