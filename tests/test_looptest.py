import json

import imageio_ffmpeg
import pytest

import config
import desktop
import loops
import looptest


@pytest.fixture
def said():
    return []


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(looptest, "SECONDS", 2)


def version():
    return json.loads((config.CONFIG_DIR / "loop-test.json").read_text("utf-8"))["version"]


def test_each_run_swaps_in_the_next_version(tmp_path, said):
    out = tmp_path / "ProPresenter Loops"
    out.mkdir()
    assert looptest.main(str(out), say=said.append) == 0
    video = out / "Smart Explorer loop test.mp4"
    assert version() == 1 and "Version 1 is in place" in said[-1]
    meta = next(imageio_ffmpeg.read_frames(str(video)))
    assert meta["size"] == (1920, 1080)
    first = video.read_bytes()
    assert looptest.main('"%s"' % out, say=said.append) == 0  # pasted with Windows' "Copy as path" quotes
    assert version() == 2 and "Version 2 is in place" in said[-1]
    assert video.read_bytes() != first
    assert sorted(p.name for p in out.iterdir()) == ["Smart Explorer loop test.mp4"]
    assert "version 2: rendered in" in (config.CONFIG_DIR / "loop-test.log").read_text("utf-8")


def test_a_video_in_use_is_tried_then_given_up_and_the_version_kept(tmp_path, said, monkeypatch):
    out = tmp_path / "Loops"
    out.mkdir()
    (out / "Smart Explorer loop test.mp4").write_bytes(b"old")
    tries = []

    def in_use(folder, name):
        tries.append(name)
        raise PermissionError(32, "in use")

    monkeypatch.setattr(loops, "put", in_use)
    clock = iter(range(0, 1000, 5))
    assert looptest.main(str(out), say=said.append, sleep=lambda s: None, clock=lambda: next(clock), try_for=20) == 1
    assert len(tries) > 1
    assert "Version 1 couldn't go in" in said[-1] and "Stop the loop in ProPresenter" in said[-1]
    assert not (config.CONFIG_DIR / "loop-test.json").exists()
    assert sorted(p.name for p in out.iterdir()) == ["Smart Explorer loop test.mp4"]  # no .part left behind
    assert (out / "Smart Explorer loop test.mp4").read_bytes() == b"old"


def test_a_folder_that_isnt_there_is_said(tmp_path, said):
    assert looptest.main(str(tmp_path / "nope"), say=said.append) == 1
    assert said == ["Loop test: can't find the folder %s." % (tmp_path / "nope")]
    assert looptest.main("", say=said.append) == 1


def test_the_app_runs_the_loop_test_from_its_command_line(monkeypatch):
    got = []
    monkeypatch.setattr(looptest, "main", lambda folder: got.append(folder) or 0)
    assert desktop.main(["--loop-test", r"C:\Loops"]) == 0
    assert desktop.main(["--loop-test"]) == 0
    assert got == [r"C:\Loops", ""]
