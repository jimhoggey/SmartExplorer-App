import json
import os
import time
from pathlib import Path

import pytest
from PIL import Image

import config
import known
import watch


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


SIZES = iter(range(1, 5000))


def png(path, color="red"):
    """A file of its own size each time: same-sized files made in the same second
    share a print, and small solid images compress to the same size."""
    Image.new("RGB", (64, 36), color).save(path)
    with open(path, "ab") as f:
        f.write(b"\0" * next(SIZES))


class Fake:
    """Stands in for OpenRouter and notifications: every file is named "Name <stem>"."""

    def __init__(self, fail_read=(), local=(), fail_name=0, refuse=None, check=None, during_read=None, name_refuse=None):
        self.reads, self.names, self.said, self.checks = [], [], [], 0
        self.fail_read, self.local, self.fail_name = set(fail_read), set(local), fail_name
        self.refuse, self.check_result, self.during_read = refuse, check, during_read
        self.name_refuse = name_refuse

    def read(self, key, model, items, profile):
        self.reads.append([it["name"] for it in items])
        if self.during_read:
            self.during_read()
        out = []
        for it in items:
            if self.refuse:
                out.append({"error": "HTTP %d" % self.refuse, "status": self.refuse})
            elif it["name"] in self.local:
                out.append({"error": "Could not read file: damaged", "local": True})
            elif it["name"] in self.fail_read:
                out.append({"error": "Model described 0 of 1 files"})
            else:
                out.append({"subject": Path(it["name"]).stem})
        return out, 0.01 * len(items)

    def name(self, key, model, items, descs, profile, existing):
        self.names.append([it["name"] for it in items])
        if self.name_refuse:
            status, self.name_refuse = self.name_refuse, None
            return {"results": [{"id": it["id"], "path": it["path"], "proposed": "raw words", "error": "HTTP %d" % status}
                                for it in items], "cost": 0.0, "name_error": "AI naming failed (HTTP %d)" % status,
                    "name_status": status}
        if self.fail_name:
            self.fail_name -= 1
            return {"results": [{"id": it["id"], "path": it["path"], "proposed": "raw words", "error": "AI naming failed"}
                                for it in items], "cost": 0.01, "name_error": "AI naming failed (HTTP 500)"}
        return {"results": [{"id": it["id"], "path": it["path"], "proposed": "Name " + d["subject"]}
                            for it, d in zip(items, descs)], "cost": 0.02, "name_error": None}

    def check(self, key):
        self.checks += 1
        return self.check_result

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "Sunday Media"
    d.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 3})
    known.record_folder(d)
    return d


def start(fake, clock=None):
    clock = clock or Clock()
    return watch.Watcher(clock=clock, say=fake.say, read=fake.read, name=fake.name, check=fake.check), clock


def run(w, clock, seconds):
    for _ in range(int(seconds // watch.POLL)):
        w.tick()
        clock.t += watch.POLL


def files(folder):
    return sorted(p.name for p in folder.iterdir())


def test_existing_files_are_left_alone(folder):
    png(folder / "old.png")
    known.record_folder(folder)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert fake.reads == [] and files(folder) == ["old.png"]
    assert fake.said == ["Smart Explorer is watching Sunday Media. New files will be renamed in 3 minutes.",
                         "Checked Sunday Media: no new files."]


def test_new_file_is_renamed_after_the_wait_and_said(folder):
    png(folder / "welcome.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 170)
    assert fake.reads == []  # still in the start-up wait
    assert watch.read_status()["message"] == "Waiting for Google Drive, 1 min left"
    run(w, clock, 60)
    assert files(folder) == ["Name welcome.png"]
    assert fake.said[1:] == ["Renaming 1 new file…", "1 file renamed and ready for ProPresenter: Name welcome."]
    run(w, clock, 600)
    assert len(fake.reads) == 1  # its new name is known: never renamed twice
    status = watch.read_status()
    assert status["state"] == "watching" and status["message"].startswith("Watching Sunday Media · last batch ")
    assert status["message"].endswith(", 1 file") and status["last_batch"]["count"] == 1
    assert watch.spent_month() == pytest.approx(0.03)
    log = (watch.watch_dir() / "watch.log").read_text("utf-8")
    assert "Renamed welcome.png -> Name welcome.png" in log


def test_files_arriving_during_the_wait_are_one_batch(folder):
    fake = Fake()
    w, clock = start(fake)
    for n in ("giving.png", "welcome.png", "sermon.png"):
        png(folder / n)
        run(w, clock, 50)
    run(w, clock, 200)
    assert fake.reads == [["giving.png", "sermon.png", "welcome.png"]]
    assert fake.said[1] == "Renaming 3 new files…"
    assert fake.said[2] == "3 files renamed and ready for ProPresenter: Name giving, Name sermon, Name welcome."


def test_first_batch_waits_for_a_quiet_minute_later_ones_for_20_seconds(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=0))
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 10)
    png(folder / "a.png")
    run(w, clock, 50)
    assert fake.reads == []  # quiet for under a minute
    run(w, clock, 25)  # a.png appeared at 10 s: its batch goes at 70 s
    assert fake.reads == [["a.png"]]
    png(folder / "b.png")
    run(w, clock, 30)
    assert fake.reads == [["a.png"], ["b.png"]]


def test_a_growing_file_waits_until_it_settles(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=0))
    fake = Fake()
    w, clock = start(fake)
    big = folder / "video.mp4"
    for i in range(30):  # Drive still downloading: it grows every look
        with open(big, "ab") as f:
            f.write(b"x" * 100)
        w.tick()
        clock.t += watch.POLL
    assert fake.reads == []
    assert watch.read_status()["message"] == "Waiting for 1 file to finish downloading"
    run(w, clock, 90)
    assert fake.reads == [["video.mp4"]]


def test_hidden_temporary_and_other_files_are_ignored(folder):
    for n in (".hidden.png", "~$x.png", "notes.txt", "part.tmp"):
        (folder / n).write_bytes(b"x")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert fake.reads == []


def test_keep_order_numbers_a_numbered_set(folder):
    for n in ("1.png", "2.png", "3.png"):
        png(folder / n)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["01 Name 1.png", "02 Name 2.png", "03 Name 3.png"]


def test_name_clash_gets_a_number_and_overwrites_nothing(folder):
    png(folder / "Name a.png", "blue")
    known.record_folder(folder)
    png(folder / "a.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["Name a (2).png", "Name a.png"]


def test_file_changed_between_reading_and_renaming_is_read_again(folder):
    png(folder / "a.png")
    fake = Fake()

    def change():
        if len(fake.reads) == 1:
            with open(folder / "a.png", "ab") as f:
                f.write(b"more")

    fake.during_read = change
    w, clock = start(fake)
    run(w, clock, 300)
    assert len(fake.reads) == 2 and files(folder) == ["Name a.png"]


def test_identical_files_in_one_batch_are_each_named_for_themselves(folder):
    png(folder / "a.png")
    (folder / "b.png").write_bytes((folder / "a.png").read_bytes())  # a duplicate upload
    st = (folder / "a.png").stat()
    os.utime(folder / "b.png", (st.st_atime, st.st_mtime))
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["Name a.png", "Name b.png"]
    assert fake.said[-1] == "2 files renamed and ready for ProPresenter: Name a, Name b."


def test_file_deleted_mid_batch_does_not_stop_the_rest(folder):
    png(folder / "a.png")
    png(folder / "b.png", "blue")
    fake = Fake(during_read=lambda: (folder / "a.png").unlink())
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["Name b.png"]
    assert fake.said[-1] == "1 file renamed and ready for ProPresenter: Name b."


def test_big_drops_go_in_batches(folder, monkeypatch):
    monkeypatch.setattr(watch, "MAX_BATCH", 2)
    for n in ("a.png", "b.png", "c.png"):
        png(folder / n)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert fake.reads == [["a.png", "b.png"], ["c.png"]]


def test_turning_watching_off_stops_it(folder):
    w, clock = start(Fake())
    assert w.tick() is True
    config.save(watch=dict(config.watch_settings(), enabled=False))
    assert w.tick() is False and watch.read_status()["state"] == "stopped"


def test_a_new_folder_starts_afresh(folder, tmp_path):
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 200)
    other = tmp_path / "Other"
    other.mkdir()
    png(other / "old.png")  # no record of this folder: what is there is left alone
    config.save(watch=dict(config.watch_settings(), folder=str(other)))
    run(w, clock, 10)
    png(other / "x.png")
    run(w, clock, 100)
    assert fake.reads == [["x.png"]] and files(other) == ["Name x.png", "old.png"]


def test_spend_is_kept_per_month_in_its_own_file(folder):
    watch.record_spend(0.5)
    watch.record_spend(0.25)
    assert watch.spent_month() == pytest.approx(0.75)
    data = json.loads((watch.watch_dir() / "spend.json").read_text())
    assert data == {time.strftime("%Y-%m"): 0.75}
    assert "config.json" not in [p.name for p in watch.watch_dir().iterdir()]


def test_log_rolls_over(monkeypatch):
    monkeypatch.setattr(watch, "LOG_LIMIT", 100)
    for i in range(20):
        watch.log("line %d" % i)
    assert (watch.watch_dir() / "watch.log.1").exists()
    assert (watch.watch_dir() / "watch.log").stat().st_size < 200


def test_text_helpers():
    assert watch._done_text(["A", "B", "C", "D", "E"], []) == \
        "5 files renamed and ready for ProPresenter: A, B, C and 2 more."
    assert watch._done_text(["A"] * 11, ["7.png"]) == \
        "11 files renamed and ready for ProPresenter. 1 couldn't be named yet: 7.png"
    assert watch._done_text([], ["7.png", "8.png"]) == "2 files couldn't be named yet: 7.png, 8.png"
    assert watch._dollars(5.0) == "US$5" and watch._dollars(2.5) == "US$2.50"
    t = time.mktime((2026, 10, 11, 8, 4, 0, 0, 0, -1))
    assert watch._clock_text(t) == "8:04am"
