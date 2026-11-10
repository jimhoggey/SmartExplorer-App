"""The start screen's Sunday check (sunday.py): a tick only for what it can see for itself."""
import time

import config
import known
import sunday
from test_watch import Fake, folder, png, run, start  # noqa: F401  (folder is a fixture)

DAY = 86400
LATER = 30 * DAY  # a "now" a month on: the files made in a test arrived before that week began


def table(*rows, times=(), enabled=True):
    return {"enabled": enabled, "rows": config.rows(list(rows)), "service_times": list(times)}


def check(s, problems=(), running=True, lines=None, recs=None, ahead=60, heartbeat=0):
    now = time.time() + ahead
    status = {"heartbeat": now - heartbeat, "problems": list(problems)}
    return sunday.check(s, status, running, False, lines or {}, recs or {}, now)


def named(tmp_path, name="Announcements", count=2):
    """A slide folder whose files are all named (known)."""
    d = tmp_path / name
    d.mkdir()
    for i in range(count):
        png(d / ("Slide %d.png" % i))
    known.record_folder(d)
    return d


def line(out, name):
    return next(r for r in out["rows"] if r["name"] == name)


def test_nothing_to_show_while_watching_is_off(tmp_path):
    assert check(table(str(named(tmp_path)), enabled=False))["state"] == "off"


def test_new_files_this_week_all_named_is_ready_for_sunday(tmp_path):
    out = check(table(str(named(tmp_path))))
    assert line(out, "Announcements") == {"name": "Announcements", "state": "ok",
                                          "text": "2 new this week, nothing waiting to be named"}
    assert out["state"] == "ok" and out["headline"] == "Ready for Sunday"
    assert out["since"] == "Over the last 7 days"


def test_nothing_new_this_week_is_said_unless_the_folder_doesnt_change_weekly(tmp_path):
    d = named(tmp_path)
    out = check(table(str(d)), ahead=LATER)
    assert line(out, "Announcements")["state"] == "warn"
    assert line(out, "Announcements")["text"] == "Nothing new over the last 7 days"
    assert out["state"] == "warn" and out["headline"] == "One thing to check before Sunday"
    out = check(table({"path": str(d), "weekly": False}), ahead=LATER)
    assert line(out, "Announcements") == {"name": "Announcements", "state": "ok",
                                          "text": "Nothing new, and it doesn't change every week"}
    assert out["headline"] == "Ready for Sunday"


def test_the_week_is_counted_from_the_end_of_the_last_service(tmp_path):
    out = check(table(str(named(tmp_path)), times=[{"day": 6, "from": "08:00", "to": "15:00"}]), ahead=LATER)
    assert out["since"].startswith("Since the end of Sunday's service, 3:00pm ")
    assert line(out, "Announcements")["text"].startswith("Nothing new since Sunday 3:00pm")


def test_files_waiting_to_be_named_are_work_or_a_problem_when_renaming_is_paused(tmp_path):
    d = named(tmp_path)
    png(d / "IMG_2231.png")
    out = check(table(str(d)))
    assert line(out, "Announcements") == {"name": "Announcements", "state": "work", "text": "1 waiting to be named"}
    assert out["state"] == "work" and out["headline"] == "Working on it"
    out = check(table(str(d)), problems=["credit"])
    assert line(out, "Announcements")["text"] == "1 waiting to be named: out of OpenRouter credit"
    assert out["state"] == "bad" and out["headline"] == "A problem to fix"


def test_a_missing_folder_or_drive_not_running_is_a_problem(tmp_path):
    out = check(table(str(tmp_path / "gone")), problems=["drive"])
    assert line(out, "gone") == {"name": "gone", "state": "bad", "text": "Can't find the folder"}
    assert line(out, "Google Drive") == {"name": "Google Drive", "state": "bad",
                                         "text": "Isn't running, so new files can't arrive"}
    assert out["headline"] == "2 problems to fix"


def test_a_loop_is_ticked_once_this_weeks_video_is_made(tmp_path):
    src = tmp_path / "PreServiceLoop"
    src.mkdir()
    row = {"path": str(src), "name": "Pre-service loop", "rename": False, "render": True, "output": str(tmp_path)}
    key = config.folder_key(str(src))
    ok = {key: {"state": "ok", "text": "Pre-service loop.mp4 · 9 screens · 2 min 05 s · made 4:12pm"}}
    made = lambda ago: {key: {"made": time.time() - ago, "screens": 9}}
    out = check(table(row), lines=ok, recs=made(DAY))
    assert line(out, "Pre-service loop.mp4")["state"] == "ok"
    assert line(out, "Pre-service loop.mp4")["text"].startswith("Video made ") and "9 screens" in line(out, "Pre-service loop.mp4")["text"]
    out = check(table(row), lines=ok, recs=made(10 * DAY))
    assert line(out, "Pre-service loop.mp4") == {"name": "Pre-service loop.mp4", "state": "warn",
                                                 "text": "Same video as last week: nothing new over the last 7 days"}
    for state, want in (("rendering", "work"), ("changed", "work"), ("held", "work"), ("none", "work"),
                        ("failed", "bad"), ("missing", "bad"), ("empty", "warn")):
        out = check(table(row), lines={key: {"state": state, "text": "what loopwatch says"}}, recs=made(DAY))
        assert line(out, "Pre-service loop.mp4")["state"] == want, state


def test_it_cant_tell_when_the_background_copy_isnt_running_or_reporting(tmp_path):
    s = table(str(named(tmp_path)))
    out = check(s, running=False)
    assert out["state"] == "bad" and out["headline"] == "Smart Explorer isn't watching"
    out = check(s, heartbeat=5 * 60)
    assert out["state"] == "unknown" and out["headline"] == "Can't tell right now: Smart Explorer hasn't checked in for 5 min"


def test_latest_says_what_was_named_newest_first_in_the_folders_own_name(tmp_path):
    d = named(tmp_path, "Sunday Slides")
    for i in range(25):
        sunday.note_named(d, [("IMG_%d.png" % i, "Slide %d" % i)], time.time() - 100 + i)
    assert len(sunday.recent()) == sunday.KEEP
    out = check(table({"path": str(d), "name": "Service slides"}))
    assert [(e["folder"], e["from"], e["to"]) for e in out["latest"]] == [
        ("Service slides", "IMG_24.png", "Slide 24"), ("Service slides", "IMG_23.png", "Slide 23"),
        ("Service slides", "IMG_22.png", "Slide 22"), ("Service slides", "IMG_21.png", "Slide 21")]


def test_the_watcher_notes_what_it_named(folder):
    png(folder / "welcome.png")
    w, clock = start(Fake())
    run(w, clock, 240)
    assert [(e["from"], e["to"]) for e in sunday.recent()] == [("welcome.png", "Name welcome")]
