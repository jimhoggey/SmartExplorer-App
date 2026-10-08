import subprocess
import sys

import autostart
import config
import desktop
import watch


def test_only_one_watcher_holds_the_lock():
    assert not watch.running()
    f = watch.take_lock()
    assert f is not None and watch.take_lock() is None and watch.running()
    watch.release(f)
    assert not watch.running()


def test_main_returns_at_once_when_another_watcher_runs():
    f = watch.take_lock()
    ticks = []

    class W:
        def tick(self):
            ticks.append(1)
            return True

    assert watch.main(sleep=lambda s: None, watcher=W()) == 0 and ticks == []
    watch.release(f)


def test_main_stops_when_watching_is_off(tmp_path):
    config.save(watch={"enabled": False})
    assert watch.main(sleep=lambda s: None) == 0
    assert not watch.running()


def test_the_stop_file_stops_main(tmp_path):
    config.save(watch={"enabled": True, "folder": str(tmp_path), "startup_wait_min": 0})
    watch.request_stop()  # left over from before: must not stop the new watcher
    looks = []

    def sleep(s):
        looks.append(1)
        if len(looks) == 3:
            watch.request_stop()

    watch.main(sleep=sleep, watcher=watch.Watcher(say=lambda t: None))
    assert len(looks) == 3 and watch.read_status()["state"] == "stopped"
    assert not (watch.watch_dir() / "stop").exists()


def test_main_survives_an_error_in_one_tick():
    calls = []

    class W:
        def tick(self):
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError("folder locked")
            return False

    assert watch.main(sleep=lambda s: None, watcher=W()) == 0 and len(calls) == 2
    assert "folder locked" in (watch.watch_dir() / "watch.log").read_text("utf-8")


def test_stop_and_wait(monkeypatch):
    assert watch.stop_and_wait() is True  # nothing running
    f = watch.take_lock()
    assert watch.stop_and_wait(timeout=0.5, sleep=lambda s: None) is False
    assert (watch.watch_dir() / "stop").exists()
    watch.release(f)


def test_spawn_starts_the_watch_command_detached(monkeypatch):
    seen = {}
    watch.request_stop()
    watch.spawn(popen=lambda argv, **kw: seen.update(argv=argv, kw=kw))
    assert seen["argv"] == autostart.watch_command(now=True)  # started from the window: no start-up wait
    assert seen["argv"][-2:] == ["--watch", "--now"]
    assert seen["kw"]["stdout"] == subprocess.DEVNULL
    assert ("start_new_session" in seen["kw"]) == (sys.platform != "win32")
    assert not (watch.watch_dir() / "stop").exists()


def test_desktop_watch_flag_runs_the_watcher(monkeypatch):
    calls = []
    monkeypatch.setattr(watch, "main", lambda now=False: calls.append(now) or 7)
    assert desktop.main(["--watch"]) == 7 and desktop.main(["--watch", "--now"]) == 7
    assert calls == [False, True]


def test_main_now_skips_the_start_up_wait(monkeypatch):
    made = []

    class W:
        def __init__(self, startup=True):
            made.append(startup)

        def tick(self):
            return False

    monkeypatch.setattr(watch, "Watcher", W)
    watch.main(sleep=lambda s: None, now=True)
    watch.main(sleep=lambda s: None)
    assert made == [False, True]
