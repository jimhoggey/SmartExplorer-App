"""Drop folders: the office drops files in one folder; Smart Explorer names each and moves it
to the folder ProPresenter's smart playlist links, so ProPresenter never sees a file renamed."""
import shutil
import time
from pathlib import Path

import pytest

import config
import known
import renamer
import sunday
import watch
from test_app import client, watcher  # noqa: F401  (fixtures)
from test_watch import Fake, png, run, start


@pytest.fixture
def drop(tmp_path):
    """Announcements - drop here → Announcements, watched, started from the window (no wait)."""
    d, ready = tmp_path / "Announcements - drop here", tmp_path / "Announcements"
    d.mkdir()
    ready.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "rows": [
        {"path": str(d), "name": "Announcements", "rename": True, "move_to": str(ready)}]})
    known.record_folder(d)
    return d, ready


def names(folder):
    return sorted(p.name for p in folder.iterdir())


def test_a_row_keeps_where_named_files_go():
    config.save(watch={"rows": [{"path": "/x/a", "move_to": ' "/x/A ready" '}, {"path": "/x/b"}]})
    assert [r["move_to"] for r in config.watch_settings()["rows"]] == ["/x/A ready", ""]


def test_plan_names_a_file_into_another_folder_without_overwriting(tmp_path):
    src, dest = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    dest.mkdir()
    for n in ("IMG_1.png", "IMG_2.png", "Welcome.png"):
        png(src / n)
    png(dest / "Welcome.png")
    items = [{"path": str(src / "IMG_1.png"), "new_name": "Welcome", "dir": str(dest)},
             {"path": str(src / "IMG_2.png"), "new_name": "Welcome", "dir": str(dest)},
             {"path": str(src / "Welcome.png"), "new_name": "Welcome", "dir": str(dest)}]  # same name, other folder: still moves
    pairs = renamer.plan(items)
    assert [Path(new).relative_to(tmp_path).as_posix() for _, new in pairs] == [
        "out/Welcome (2).png", "out/Welcome (3).png", "out/Welcome (4).png"]
    renamer.apply(pairs, tmp_path / "journal")
    assert names(src) == [] and names(dest) == ["Welcome (2).png", "Welcome (3).png", "Welcome (4).png", "Welcome.png"]


def test_the_watcher_names_a_dropped_file_and_moves_it_on(drop):
    d, ready = drop
    png(d / "welcome.png")
    keep = d.parent / "copy.png"
    shutil.copy2(d / "welcome.png", keep)
    w, clock = start(Fake())
    w.startup = False
    run(w, clock, 90)
    assert names(d) == [] and names(ready) == ["Name welcome.png"]
    assert [(e["from"], e["to"]) for e in sunday.recent()] == [("welcome.png", "Name welcome")]
    shutil.copy2(keep, d / "welcome.png")  # the very same file dropped again later: moved on again
    run(w, clock, 120)
    assert names(d) == [] and names(ready) == ["Name welcome (2).png", "Name welcome.png"]


def test_save_checks_where_named_files_go(client, watcher, tmp_path):  # noqa: F811
    d, ready = tmp_path / "Drop", tmp_path / "Ready"
    d.mkdir()
    row = {"path": str(d), "name": "Announcements", "rename": True}

    def save(**kw):
        return client.post("/api/watch", json={"enabled": True, "rows": [dict(row, **kw)]})

    r = save(move_to=str(ready))
    assert r.status_code == 400 and "Can't move files into Ready" in r.get_json()["error"]
    ready.mkdir()
    r = save(move_to=str(d))
    assert r.status_code == 400 and "a different folder" in r.get_json()["error"]
    r = save(move_to=str(ready))
    assert r.status_code == 200 and r.get_json()["settings"]["rows"][0]["move_to"] == str(ready)
    other = tmp_path / "Watched"
    other.mkdir()
    r = client.post("/api/watch", json={"enabled": True, "rows": [dict(row, move_to=str(other)), str(other)]})
    assert r.status_code == 400 and "doesn't watch" in r.get_json()["error"]


def test_the_sunday_check_counts_what_reached_the_playlists_folder(drop):
    d, ready = drop
    png(ready / "Name welcome.png")
    s = config.watch_settings()
    out = sunday.check(s, {"heartbeat": time.time(), "problems": []}, True, False, {}, {}, time.time() + 60)
    row = out["rows"][0]
    assert row["state"] == "ok" and row["text"] == "1 new this week, nothing waiting to be named"
    assert "1 file in Announcements" in row["detail"]
    png(d / "IMG_9.png")
    out = sunday.check(s, {"heartbeat": time.time(), "problems": []}, True, False, {}, {}, time.time() + 60)
    assert out["rows"][0]["text"] == "1 waiting to be named"
