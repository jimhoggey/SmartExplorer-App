"""Fixes from the whole-branch review of background renaming: what an unattended
watcher must do when local writes fail, folders misbehave or people step in."""
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
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 0})
    known.record_folder(d)
    png(d / "welcome.png")
    return d


def test_spend_that_cannot_be_saved_does_not_repeat_the_batch(folder, monkeypatch):
    def full_disk(usd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(watch, "record_spend", full_disk)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert len(fake.reads) == 1 and files(folder) == ["Name welcome.png"]


def test_a_rename_that_cannot_be_recorded_is_not_renamed_again(folder, monkeypatch):
    def broken(*a, **k):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(known, "add", broken)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert len(fake.reads) == 1 and files(folder) == ["Name welcome.png"]


def test_an_error_after_paying_counts_as_a_paid_attempt(folder):
    (config.CONFIG_DIR / "journal").write_text("not a folder")  # the undo record cannot be written
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 3600)
    assert len(fake.reads) == 1 and len(fake.names) == 2  # paid descriptions kept, then left alone
    assert files(folder) == ["welcome.png"]
    assert "Couldn't name welcome.png" in fake.said[-1]


def test_a_journal_that_cannot_be_written_after_renaming_keeps_the_renames(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    blocked = tmp_path / "journal"
    out = renamer.apply([(str(tmp_path / "a.png"), str(tmp_path / "b.png"))], journal_dir=blocked)
    assert out["renamed"] == 1 and (tmp_path / "b.png").exists()  # the folder was made, the file wasn't
    blocked2 = tmp_path / "j2"
    blocked2.mkdir()
    (blocked2 / "x").mkdir()
    real = renamer.Path.write_text

    def fail(self, *a, **k):
        if self.parent == blocked2:
            raise OSError(28, "No space left on device")
        return real(self, *a, **k)

    renamer.Path.write_text = fail
    try:
        out = renamer.apply([(str(tmp_path / "b.png"), str(tmp_path / "c.png"))], journal_dir=blocked2)
    finally:
        renamer.Path.write_text = real
    assert out["renamed"] == 1 and (tmp_path / "c.png").exists() and "undo" in out["error"]


def test_a_folder_that_cannot_be_read_is_a_problem_not_an_empty_folder(folder, monkeypatch):
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 5)
    real = known.new_files

    def denied(f):
        raise PermissionError(13, "Permission denied", str(f))

    monkeypatch.setattr(known, "new_files", denied)
    run(w, clock, 300)
    assert fake.reads == [] and "Checked Sunday Media: no new files." not in fake.said
    assert fake.said[-1] == watch.PROBLEMS["listing"].format(folder="Sunday Media")
    assert watch.read_status()["message"] == "Paused: can't open Sunday Media"
    assert "Permission denied" in (watch.watch_dir() / "watch.log").read_text("utf-8")
    monkeypatch.setattr(known, "new_files", real)
    run(w, clock, 120)
    assert files(folder) == ["Name welcome.png"]


def test_listing_a_missing_folder_raises(tmp_path):
    with pytest.raises(OSError):
        known.visible(tmp_path / "missing")


def test_no_record_of_the_folder_leaves_its_files_alone(folder):
    known._path().unlink()  # deleted, or lost in a power cut
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert fake.reads == [] and files(folder) == ["welcome.png"]
    png(folder / "giving.png", "blue")
    run(w, clock, 120)
    assert files(folder) == ["Name giving.png", "welcome.png"]


def test_a_waiting_file_renamed_by_hand_is_left_alone(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=3))
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 60)
    (folder / "welcome.png").rename(folder / "Welcome Slide.png")
    run(w, clock, 600)
    assert fake.reads == [] and files(folder) == ["Welcome Slide.png"]


def test_a_given_up_file_renamed_by_hand_is_left_alone(folder):
    fake = Fake(fail_name=5)
    w, clock = start(fake)
    run(w, clock, 3600)
    assert len(fake.names) == 2
    (folder / "welcome.png").rename(folder / "Announcements.png")
    run(w, clock, 600)
    assert len(fake.names) == 2 and files(folder) == ["Announcements.png"]


def test_a_refusal_while_naming_costs_no_attempt(folder):
    fake = Fake(name_refuse=402)
    w, clock = start(fake)
    run(w, clock, 90)
    assert w.failures == {} and watch.PROBLEMS["credit"] in fake.said
    assert not any(s.startswith("Couldn't") or "couldn't" in s for s in fake.said)
    run(w, clock, 900)
    assert files(folder) == ["Name welcome.png"] and len(fake.reads) == 1


def test_a_deleted_files_name_is_forgotten_after_ten_minutes(tmp_path):
    d = tmp_path / "Sunday Media"
    d.mkdir()
    png(d / "1.png")  # an old raw export, there when watching was turned on
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 0})
    known.record_folder(d)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 30)
    (d / "1.png").unlink()
    run(w, clock, 60)
    png(d / "1.png", "blue")  # back within a minute: Drive replacing it, say
    run(w, clock, 300)
    assert fake.reads == []
    (d / "1.png").unlink()
    run(w, clock, 700)
    png(d / "1.png", "green")  # next week's export with the same default name
    run(w, clock, 120)
    assert fake.reads == [["1.png"]] and files(d) == ["Name 1.png"]


def test_a_short_disappearance_mid_run_is_not_announced(folder):
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    away = folder.with_name("away")
    folder.rename(away)
    run(w, clock, 60)  # Google Drive restarting
    away.rename(folder)
    run(w, clock, 60)
    assert not any("can't find" in s for s in fake.said)
    folder.rename(away)
    run(w, clock, 200)
    assert fake.said.count(watch.PROBLEMS["folder"].format(folder="Sunday Media")) == 1


@pytest.fixture
def drive_folder(tmp_path):
    d = tmp_path / "My Drive" / "Sunday Media"
    d.mkdir(parents=True)
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 3})
    known.record_folder(d)
    return d


class Drive:
    def __init__(self, up):
        self.up, self.asked = up, 0

    def __call__(self):
        self.asked += 1
        return self.up


def drive_watcher(fake, up):
    from test_watch import Clock
    d = Drive(up)
    return watch.Watcher(clock=Clock(), say=fake.say, read=fake.read, name=fake.name, check=fake.check,
                         drive=d), d


def test_google_drive_not_running_is_said_once_after_the_wait(drive_folder):
    fake = Fake()
    w, d = drive_watcher(fake, False)
    run(w, w.clock, 295)  # the start-up wait (3 min) plus 2 minutes for Drive to start
    assert not any("Google Drive" in s for s in fake.said)
    run(w, w.clock, 60)
    msg = watch.PROBLEMS["drive"].format(folder="Sunday Media")
    assert fake.said.count(msg) == 1 and "Checked Sunday Media: no new files." not in fake.said
    status = watch.read_status()
    assert status["state"] == "warning" and status["message"] == "Watching Sunday Media · Google Drive isn't running"
    run(w, w.clock, 600)
    assert fake.said.count(msg) == 1


def test_files_are_still_renamed_while_google_drive_is_down(drive_folder):
    fake = Fake()
    w, d = drive_watcher(fake, False)
    png(drive_folder / "welcome.png")
    run(w, w.clock, 300)
    assert files(drive_folder) == ["Name welcome.png"]


def test_the_warning_clears_when_google_drive_starts(drive_folder):
    fake = Fake()
    w, d = drive_watcher(fake, False)
    run(w, w.clock, 400)
    d.up = True
    run(w, w.clock, 60)
    assert watch.read_status()["state"] == "watching" and "drive" not in w.problems
    d.up = False
    run(w, w.clock, 200)
    assert fake.said.count(watch.PROBLEMS["drive"].format(folder="Sunday Media")) == 2


def test_google_drive_is_asked_every_30_seconds_and_only_for_drive_folders(drive_folder, tmp_path):
    fake = Fake()
    w, d = drive_watcher(fake, True)
    run(w, w.clock, 300)
    assert d.asked == 10  # 300 s / 30 s, not once per 5-second look
    plain = tmp_path / "Media"
    plain.mkdir()
    config.save(watch=dict(config.watch_settings(), folder=str(plain)))
    d.asked = 0
    run(w, w.clock, 300)
    assert d.asked == 0


def test_unknown_drive_state_says_nothing(drive_folder):
    fake = Fake()
    w, d = drive_watcher(fake, None)
    run(w, w.clock, 900)
    assert not any("Google Drive" in s for s in fake.said)


def test_a_starting_watcher_waits_for_a_brief_lock(monkeypatch):
    real = watch.take_lock
    tries = []

    def busy_then_free():
        tries.append(1)
        return None if len(tries) < 3 else real()  # the window was checking running()

    monkeypatch.setattr(watch, "take_lock", busy_then_free)
    ticks = []

    class W:
        def tick(self):
            ticks.append(1)
            return False

    assert watch.main(sleep=lambda s: None, watcher=W()) == 0 and ticks == [1]
