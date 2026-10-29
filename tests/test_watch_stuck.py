"""A file that can't be renamed because it is open in another program: the chosen
name is kept, it is said once, and renaming it again never asks the AI again."""
import os
from pathlib import Path

import pytest

import config
import known
import renamer
import watch
from test_watch import Fake, files, png, run, start


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "Sunday Media"
    d.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "folders": [str(d)], "startup_wait_min": 0})
    known.record_folder(d)
    return d


class Lock:
    """Files another program holds open, as Windows refuses to rename them."""

    def __init__(self, monkeypatch, *names):
        self.names = set(names)
        real = os.rename

        def rename(old, new):
            if Path(old).name in self.names:
                e = PermissionError(13, "The process cannot access the file because it is being used by another process")
                e.winerror = 32
                raise e
            real(old, new)

        monkeypatch.setattr(renamer.os, "rename", rename)


def test_a_file_in_use_keeps_its_chosen_name_and_is_renamed_without_the_ai(folder, monkeypatch):
    png(folder / "welcome.png")
    png(folder / "giving.png", "blue")
    lock = Lock(monkeypatch, "welcome.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 90)
    assert files(folder) == ["Name giving.png", "welcome.png"]  # the rest is renamed
    stuck = [s for s in fake.said if "open in another program" in s]
    assert stuck == ["Couldn't rename welcome.png: it's open in another program (ProPresenter, say). Close it there; "
                     "Smart Explorer tries again every minute, or click Try again in Smart Explorer."]
    status = watch.read_status()
    assert status["state"] == "warning" and status["stuck"] == 1
    assert status["message"] == "Watching Sunday Media · 1 file couldn't be renamed: it's open in another program"
    run(w, clock, 300)
    assert len(fake.said) == len(set(fake.said))  # said once, not every minute
    lock.names.clear()  # closed in ProPresenter
    run(w, clock, 65)
    assert files(folder) == ["Name giving.png", "Name welcome.png"]
    assert len(fake.reads) == 1 and len(fake.names) == 1  # never asked the AI again
    assert "Renamed welcome.png to Name welcome: ready for ProPresenter." in fake.said
    assert watch.read_status()["stuck"] == 0 and known.new_files(folder) == []


def test_try_again_renames_at_once(folder, monkeypatch):
    png(folder / "welcome.png")
    lock = Lock(monkeypatch, "welcome.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 70)
    lock.names.clear()
    watch.request_retry()  # the Try again button
    run(w, clock, 5)  # one look, long before the minute is up
    assert files(folder) == ["Name welcome.png"]
    assert not (watch.watch_dir() / "retry").exists()


def test_a_stuck_file_never_counts_as_a_paid_attempt(folder, monkeypatch):
    png(folder / "welcome.png")
    Lock(monkeypatch, "welcome.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 3600)
    assert w.failures == {} and len(fake.names) == 1 and not any(s.startswith("Couldn't name") for s in fake.said)
