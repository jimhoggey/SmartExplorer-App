"""Loop videos in the background, with a fake renderer and clock: when a render starts,
when it is held, what is said, and how the swap is tried again."""
import json
import time
from pathlib import Path

import pytest
from PIL import Image

import config
import loops
import loopwatch
import watch

SUNDAY_7AM = time.mktime((2026, 11, 8, 7, 0, 0, 0, 0, -1))  # 8 Nov 2026 is a Sunday


class Proc:
    def __init__(self, code):
        self.code, self.done, self.killed = code, False, False

    def poll(self):
        return self.code if self.done or self.killed else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.code


class Render:
    """Stands in for ffmpeg: writes a small render.mp4 and a process the test finishes."""

    def __init__(self):
        self.calls, self.procs, self.code, self.instant = [], [], 0, True

    def __call__(self, paths, work):
        self.calls.append([p.name for p in paths])
        (Path(work) / "render.mp4").write_bytes(b"render %d" % len(self.calls))
        proc = Proc(self.code)
        proc.done = self.instant
        self.procs.append(proc)
        return proc, 10.0 * len(paths) - (len(paths) - 1), []


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "_say", lambda text: None)
    src = tmp_path / "PreServiceLoop"
    src.mkdir()
    for n in ("1 Welcome.png", "2 Cafe.png"):
        Image.new("RGB", (40, 20), "teal").save(src / n)
    out = tmp_path / "ProPresenter Loops"
    out.mkdir()
    row = {"path": str(src), "name": "Pre-service loop", "rename": False, "render": True, "output": str(out)}
    config.save(watch={"enabled": True, "rows": [row], "startup_wait_min": 0})
    clock = [SUNDAY_7AM]
    said, render = [], Render()
    w = watch.Watcher(clock=lambda: clock[0], say=said.append, render=render, startup=False, drive=lambda: True)
    return {"src": src, "out": out, "row": row, "clock": clock, "said": said, "render": render, "w": w,
            "video": out / "Pre-service loop.mp4"}


def run(t, seconds, step=5):
    for _ in range(int(seconds / step)):
        t["w"].tick()
        t["clock"][0] += step


def status():
    return watch.read_status()


def loop_state():
    return status()["loops"][0]


def test_a_new_loop_renders_after_a_quiet_half_minute_and_is_swapped_in(setup):
    t = setup
    run(t, 25)
    assert t["render"].calls == [] and loop_state()["state"] == "changed"
    assert "Rendering in" in status()["message"]
    run(t, 10)
    assert t["render"].calls == [["1 Welcome.png", "2 Cafe.png"]]
    assert t["video"].read_bytes() == b"render 1"
    assert t["said"][-1] == "Pre-service loop updated: 2 screens, 19 s."
    assert loop_state()["state"] == "ok" and loop_state()["text"].startswith("Pre-service loop.mp4 · 2 screens · 19 s · made ")
    assert status()["message"] == "Pre-service loop up to date" and status()["state"] == "watching"
    assert sorted(p.name for p in t["out"].iterdir()) == ["Pre-service loop.mp4"]
    rec = loopwatch.records()[config.folder_key(t["row"]["path"])]
    assert rec["screens"] == 2 and rec["name"] == "Pre-service loop" and len(rec["files"]) == 2


def test_nothing_changed_renders_nothing_even_after_a_restart(setup):
    t = setup
    run(t, 40)
    t["w"] = watch.Watcher(clock=lambda: t["clock"][0], say=t["said"].append, render=t["render"], startup=False)
    run(t, 120)
    assert len(t["render"].calls) == 1


@pytest.mark.parametrize("change", ["add", "delete", "rename", "edit"])
def test_any_change_to_the_screens_renders_again(setup, change):
    t = setup
    run(t, 40)
    src = t["src"]
    if change == "add":
        Image.new("RGB", (40, 20), "red").save(src / "3 Youth Camp.png")
    elif change == "delete":
        (src / "2 Cafe.png").unlink()
    elif change == "rename":
        (src / "2 Cafe.png").rename(src / "2 Cafe 2026.png")
    else:
        Image.new("RGB", (80, 40), "red").save(src / "2 Cafe.png")
    run(t, 25)
    assert len(t["render"].calls) == 1  # still settling
    run(t, 10)
    assert len(t["render"].calls) == 2 and t["video"].read_bytes() == b"render 2"


def test_a_missing_video_is_rendered_again(setup):
    t = setup
    run(t, 40)
    t["video"].unlink()
    run(t, 35)
    assert len(t["render"].calls) == 2 and t["video"].is_file()


def test_a_change_during_a_render_stops_it_and_renders_again(setup):
    t = setup
    t["render"].instant = False
    run(t, 35)
    first = t["render"].procs[0]
    assert loop_state()["state"] == "rendering"
    Image.new("RGB", (40, 20), "red").save(t["src"] / "3 Youth Camp.png")
    run(t, 5)
    assert first.killed and not t["video"].exists()
    run(t, 35)
    assert len(t["render"].calls) == 2
    t["render"].procs[-1].done = True
    run(t, 5)
    assert t["video"].read_bytes() == b"render 2"


def test_service_times_hold_a_render_and_a_running_one_is_stopped(setup):
    t = setup
    config.save(watch=dict(config.watch_settings(), service_times=[{"day": 6, "from": "08:00", "to": "15:00"}]))
    t["clock"][0] = SUNDAY_7AM + 59 * 60 - 40  # 7:58:20
    t["render"].instant = False
    run(t, 40)  # renders from 7:58:50
    assert len(t["render"].calls) == 1
    run(t, 70)  # 8:00 comes
    assert t["render"].procs[0].killed and loop_state()["state"] == "held"
    assert status()["message"] == "Pre-service loop will be updated after the service, at 3:00pm"
    run(t, 3600)
    assert len(t["render"].calls) == 1 and not t["video"].exists()
    t["clock"][0] = SUNDAY_7AM + 8 * 3600  # 3:00pm
    t["render"].instant = True
    run(t, 10)
    assert len(t["render"].calls) == 2 and t["video"].is_file()


def test_render_now_in_a_service_time_renders_and_swaps_at_once(setup):
    t = setup
    config.save(watch=dict(config.watch_settings(), service_times=[{"day": 6, "from": "07:00", "to": "15:00"}]))
    run(t, 60)
    assert t["render"].calls == []
    loopwatch.request(t["row"]["path"], anyway=True)
    run(t, 5)
    assert len(t["render"].calls) == 1 and t["video"].is_file()


def test_render_now_renders_when_nothing_changed(setup):
    t = setup
    run(t, 40)
    loopwatch.request(t["row"]["path"])
    run(t, 5)
    assert len(t["render"].calls) == 2


def test_a_video_in_use_is_tried_every_minute_and_said_once_after_ten(setup, monkeypatch):
    t = setup
    run(t, 40)
    Image.new("RGB", (40, 20), "red").save(t["src"] / "3 Youth Camp.png")
    tries = []
    real = loops.put

    def in_use(folder, name):
        tries.append(t["clock"][0])
        raise PermissionError(32, "in use")

    monkeypatch.setattr(loops, "put", in_use)
    run(t, 35)
    assert len(tries) == 1 and loop_state()["state"] == "staged"
    assert status()["message"] == "New Pre-service loop is ready: waiting for ProPresenter to let go of the old one"
    assert (t["out"] / "Pre-service loop.mp4.part").read_bytes() == b"render 2"
    run(t, 600)
    assert 10 <= len(tries) <= 11 and all(b - a == 60 for a, b in zip(tries, tries[1:]))
    in_use_said = [s for s in t["said"] if "still using" in s]
    assert in_use_said == ["ProPresenter is still using Pre-service loop.mp4. The new one goes in as soon as it stops playing."]
    run(t, 300)
    assert len([s for s in t["said"] if "still using" in s]) == 1
    monkeypatch.setattr(loops, "put", real)
    run(t, 60)
    assert t["video"].read_bytes() == b"render 2" and t["said"][-1] == "Pre-service loop updated: 3 screens, 28 s."
    assert sorted(p.name for p in t["out"].iterdir()) == ["Pre-service loop.mp4"]


def test_a_failed_render_keeps_the_old_video_and_tries_again_later(setup, monkeypatch):
    t = setup
    run(t, 40)
    t["render"].code = 1
    monkeypatch.setattr(loops, "tail", lambda work: "frame=0\nNo space left on device")
    Image.new("RGB", (40, 20), "red").save(t["src"] / "3 Youth Camp.png")
    run(t, 35)
    assert t["video"].read_bytes() == b"render 1"
    assert t["said"][-1] == ("Couldn't update Pre-service loop: the disk is full. The old video is still in place. "
                             "Smart Explorer will try again in 5 minutes.")
    assert loop_state()["state"] == "failed" and status()["state"] == "warning"
    assert loop_state()["text"].startswith("Last render failed: the disk is full. Trying again at ")
    run(t, 290)
    assert len(t["render"].calls) == 2
    run(t, 10)
    assert len(t["render"].calls) == 3 and sum("Couldn't update" in s for s in t["said"]) == 1
    t["render"].code = 0
    Image.new("RGB", (40, 20), "blue").save(t["src"] / "4 Kids.png")  # a change: tried after it settles, not in 30 minutes
    run(t, 35)
    assert len(t["render"].calls) == 4 and t["video"].read_bytes() == b"render 4"
    (t["src"] / "3 Youth Camp.png").unlink()
    (t["src"] / "4 Kids.png").unlink()  # deleted screens leave the video too
    run(t, 60)
    assert len(t["render"].calls) == 5 and t["render"].calls[-1] == ["1 Welcome.png", "2 Cafe.png"]


def test_an_empty_folder_keeps_the_old_video_and_says_so_once(setup):
    t = setup
    run(t, 40)
    for p in t["src"].iterdir():
        p.unlink()
    run(t, 120)
    assert t["said"].count("Pre-service loop's folder is empty, so the old video was kept.") == 1
    assert t["video"].read_bytes() == b"render 1" and len(t["render"].calls) == 1


def test_a_missing_loop_folder_is_said_after_two_minutes(setup):
    t = setup
    run(t, 40)
    for p in t["src"].iterdir():
        p.unlink()
    t["src"].rmdir()
    run(t, 115)
    assert not any("can't find the folder" in s for s in t["said"])
    run(t, 10)
    assert t["said"][-1] == "Smart Explorer can't find the folder for Pre-service loop. Check Google Drive is running and signed in."
    assert status()["state"] == "warning" and t["video"].is_file()


def test_a_missing_save_to_folder_is_said(setup):
    t = setup
    t["out"].rmdir()
    run(t, 40)
    assert t["said"][-1] == "Smart Explorer can't save Pre-service loop into ProPresenter Loops. Check the folder is there."
    assert t["render"].calls == []


def test_loops_take_turns(setup, tmp_path):
    t = setup
    post = tmp_path / "EndServiceLoop"
    post.mkdir()
    Image.new("RGB", (40, 20), "navy").save(post / "Farewell.png")
    second = dict(t["row"], path=str(post), name="Post-service loop")
    config.save(watch=dict(config.watch_settings(), rows=[t["row"], second]))
    t["render"].instant = False
    run(t, 40)
    assert len(t["render"].calls) == 1
    assert status()["loops"][1]["state"] == "turn" and status()["loops"][1]["text"] == "Renders after Pre-service loop"
    t["render"].procs[0].done = True
    run(t, 10)
    assert len(t["render"].calls) == 2 and t["render"].calls[1] == ["Farewell.png"]


def test_a_loop_waits_for_its_new_files_to_be_renamed(setup, monkeypatch):
    t = setup
    config.save(watch=dict(config.watch_settings(), rows=[dict(t["row"], rename=True)]))
    monkeypatch.setattr(t["w"], "_renaming", lambda path: True)
    run(t, 60)
    assert t["render"].calls == [] and loop_state()["text"] == "Waiting for its new files to be renamed"


def test_loops_render_without_an_openrouter_key(setup, tmp_path):
    t = setup
    media = tmp_path / "Sunday Media"
    media.mkdir()
    config.save(watch=dict(config.watch_settings(), rows=[t["row"], str(media)]))
    run(t, 120)
    Image.new("RGB", (40, 20), "red").save(media / "new.png")  # renaming can't run: no key
    run(t, 90)
    assert any("no OpenRouter key" in s for s in t["said"])
    assert len(t["render"].calls) == 1 and t["video"].is_file()


def test_a_new_name_renders_under_it_and_leaves_the_old_video(setup):
    t = setup
    run(t, 40)
    config.save(watch=dict(config.watch_settings(), rows=[dict(t["row"], name="Walk-in loop")]))
    run(t, 40)
    assert (t["out"] / "Walk-in loop.mp4").is_file() and t["video"].is_file()


def test_removing_a_loop_stops_its_render(setup):
    t = setup
    t["render"].instant = False
    run(t, 35)
    config.save(watch=dict(config.watch_settings(), rows=[]))
    run(t, 5)
    assert t["render"].procs[0].killed


def test_the_window_shows_the_live_line_or_the_last_video(setup):
    t = setup
    s = config.watch_settings()
    k = config.folder_key(t["row"]["path"])
    assert loopwatch.lines(s, {}, running=False) == {k: {"state": "none", "text": "Not rendered yet"}}
    run(t, 40)
    assert loopwatch.lines(s, status(), running=True)[k]["state"] == "ok"
    off = loopwatch.lines(s, {}, running=False)[k]
    assert off["state"] == "ok" and off["text"].startswith("Pre-service loop.mp4 · 2 screens")
    t["video"].unlink()
    assert loopwatch.lines(s, {}, running=False)[k]["text"] == "Not rendered yet"


def test_the_real_renderer_reports_screens_it_could_not_read(setup, tmp_path):
    (setup["src"] / "3 broken.png").write_bytes(b"not a picture")
    work = loops.fresh(tmp_path / "work")
    proc, total, left_out = loopwatch._render(loops.screens(setup["src"]), work)
    assert proc.wait(timeout=300) == 0 and total == 19
    assert [p.name for p, _ in left_out] == ["3 broken.png"]
    proc, total, left_out = loopwatch._render([setup["src"] / "3 broken.png"], loops.fresh(tmp_path / "w2"))
    assert proc is None and len(left_out) == 1
