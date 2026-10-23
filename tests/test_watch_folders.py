"""Background renaming watching several folders at once."""
import pytest

import config
import known
import watch
from test_watch import Clock, Fake, files, png, run


@pytest.fixture
def two(tmp_path):
    a, b = tmp_path / "Sunday Media", tmp_path / "Youth Media"
    a.mkdir()
    b.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "folders": [str(a), str(b)], "startup_wait_min": 0})
    known.record_folder(a)
    known.record_folder(b)
    return a, b


def start(fake):
    return watch.Watcher(clock=Clock(), say=fake.say, read=fake.read, name=fake.name, check=fake.check,
                         drive=lambda: None)


def add_folder(path):
    s = config.watch_settings()
    config.save(watch=dict(s, folders=s["folders"] + [str(path)]))


def test_each_folder_is_named_in_its_own_batch(two):
    a, b = two
    png(a / "giving.png")
    png(b / "games.png", "blue")
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 90)
    assert fake.reads == [["giving.png"], ["games.png"]]  # never one batch across folders
    assert files(a) == ["Name giving.png"] and files(b) == ["Name games.png"]
    assert fake.said[0] == "Smart Explorer is watching Sunday Media and Youth Media. New files will be renamed as they arrive."
    assert "Renaming 1 new file in Sunday Media…" in fake.said
    assert "1 file renamed and ready for ProPresenter in Youth Media: Name games." in fake.said
    message = watch.read_status()["message"]
    assert message.startswith("Watching 2 folders · last batch ") and message.endswith(", 1 file in Youth Media")


def test_names_avoid_only_their_own_folders_files(two):
    a, b = two
    png(b / "Name giving.png", "green")  # taken in Youth Media, free in Sunday Media
    known.record_folder(b)
    png(a / "giving.png")
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 90)
    assert files(a) == ["Name giving.png"]


def test_nothing_new_is_said_once_for_all_folders(two):
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 60)
    assert fake.said == ["Smart Explorer is watching Sunday Media and Youth Media. New files will be renamed as they arrive.",
                         "Checked Sunday Media and Youth Media: no new files."]


def test_three_or_more_folders_are_counted(two, tmp_path):
    kids = tmp_path / "Kids"
    kids.mkdir()
    known.record_folder(kids)
    add_folder(kids)
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 30)
    assert fake.said == ["Smart Explorer is watching 3 folders. New files will be renamed as they arrive.",
                         "Checked 3 folders: no new files."]


def test_a_missing_folder_does_not_stop_the_others(two):
    a, b = two
    a.rename(a.with_name("Sunday Media (signed out)"))
    png(b / "games.png")
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 300)
    assert files(b) == ["Name games.png"]
    assert fake.said.count(watch.PROBLEMS["folder"].format(folder="Sunday Media")) == 1
    status = watch.read_status()
    assert status["state"] == "warning" and status["message"] == "Watching 2 folders · can't find Sunday Media"


def test_files_already_in_an_added_folder_are_left_alone(two, tmp_path):
    kids = tmp_path / "Kids"
    kids.mkdir()
    png(kids / "old.png")
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 30)
    add_folder(kids)  # no record yet: what is there is recorded, not renamed
    run(w, w.clock, 30)
    png(kids / "new.png", "blue")
    run(w, w.clock, 120)
    assert files(kids) == ["Name new.png", "old.png"]


def test_a_removed_folder_is_no_longer_watched(two):
    a, b = two
    fake = Fake()
    w = start(fake)
    run(w, w.clock, 30)
    config.save(watch=dict(config.watch_settings(), folders=[str(a)]))
    run(w, w.clock, 10)
    png(b / "games.png")
    run(w, w.clock, 200)
    assert files(b) == ["games.png"] and fake.reads == []


def test_failures_are_kept_per_folder(two):
    a, b = two
    png(a / "giving.png")
    png(b / "games.png", "blue")
    fake = Fake(fail_read={"games.png"})
    w = start(fake)
    run(w, w.clock, 90)
    assert files(a) == ["Name giving.png"] and files(b) == ["games.png"]
    assert len(w.failures) == 1 and "1 file couldn't be named yet in Youth Media: games.png" in fake.said
