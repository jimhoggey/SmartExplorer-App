import time

import pytest

import config
import known
import namer
import watch
from test_watch import Clock, Fake, files, png, run, start


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "Sunday Media"
    d.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 0})
    known.record_folder(d)
    png(d / "welcome.png")
    return d


def test_failed_naming_reruns_naming_only_and_never_renames_with_a_guess(folder):
    fake = Fake(fail_name=1)
    w, clock = start(fake)
    run(w, clock, 90)
    assert files(folder) == ["welcome.png"] and len(fake.reads) == 1 and len(fake.names) == 1
    assert fake.said[-1] == "1 file couldn't be named yet: welcome.png"
    run(w, clock, 300)
    assert len(fake.reads) == 1 and len(fake.names) == 2  # paid descriptions kept: naming only
    assert files(folder) == ["Name welcome.png"]


def test_two_paid_failures_leave_the_file_until_the_next_start_up(folder):
    fake = Fake(fail_name=5)
    w, clock = start(fake)
    run(w, clock, 3600)
    assert len(fake.names) == 2 and files(folder) == ["welcome.png"]
    assert fake.said[-1] == "Couldn't name welcome.png. It's still in Sunday Media under its old name."
    w2, clock = start(fake, clock)  # the next start-up tries again
    run(w2, clock, 90)
    assert len(fake.names) == 3


def test_a_file_the_model_cannot_read_counts_as_paid(folder):
    fake = Fake(fail_read={"welcome.png"})
    w, clock = start(fake)
    run(w, clock, 3600)
    assert len(fake.reads) == 2 and fake.names == []
    assert "Couldn't name welcome.png" in fake.said[-1]


def test_a_file_that_cannot_be_opened_here_is_tried_three_times(folder):
    fake = Fake(local={"welcome.png"})
    w, clock = start(fake)
    run(w, clock, 90)
    assert len(fake.reads) == 1
    run(w, clock, 300)
    assert len(fake.reads) == 2
    run(w, clock, 1800)
    assert len(fake.reads) == 3 and "Couldn't name welcome.png" in fake.said[-1]
    run(w, clock, 3600)
    assert len(fake.reads) == 3


def test_free_check_failure_sends_nothing_and_checks_again_later(folder):
    fake = Fake(check="connection")
    w, clock = start(fake)
    run(w, clock, 120)
    assert fake.reads == [] and fake.checks == 1
    assert fake.said[-1] == watch.PROBLEMS["connection"]
    assert watch.read_status()["message"] == "Paused: can't reach OpenRouter"
    run(w, clock, 240)
    assert fake.checks == 1  # every 5 minutes, not every look
    fake.check_result = None
    run(w, clock, 60)
    assert fake.checks == 2 and files(folder) == ["Name welcome.png"]
    assert fake.said.count(watch.PROBLEMS["connection"]) == 1


def test_out_of_credit_is_said_once_and_checked_every_15_minutes(folder):
    fake = Fake(check="credit")
    w, clock = start(fake)
    run(w, clock, 965)  # first check at 60 s, the next one 15 minutes later
    assert fake.checks == 2 and fake.reads == []
    assert fake.said.count(watch.PROBLEMS["credit"]) == 1


def test_a_refused_request_costs_no_attempt(folder):
    fake = Fake(refuse=402)
    w, clock = start(fake)
    run(w, clock, 90)
    assert len(fake.reads) == 1 and w.failures == {} and watch.PROBLEMS["credit"] in fake.said
    fake.refuse = None
    run(w, clock, 900)
    assert files(folder) == ["Name welcome.png"]


def test_a_problem_is_said_again_after_it_cleared_and_came_back(folder):
    fake = Fake(check="connection")
    w, clock = start(fake)
    run(w, clock, 90)
    fake.check_result = None
    run(w, clock, 300)
    png(folder / "giving.png", "blue")
    fake.check_result = "connection"
    run(w, clock, 60)
    assert fake.said.count(watch.PROBLEMS["connection"]) == 2


def test_monthly_limit_pauses_until_raised(folder):
    config.write_json(watch.watch_dir() / "spend.json", {time.strftime("%Y-%m"): 5.0})
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 120)
    assert fake.reads == [] and fake.checks == 0
    assert fake.said[-1] == "Background renaming has reached this month's US$5 limit. Raise it in Settings to carry on."
    assert watch.read_status()["message"] == "Paused: this month's US$5 limit is reached"
    config.save(watch=dict(config.watch_settings(), monthly_limit_usd=10))
    run(w, clock, 30)
    assert files(folder) == ["Name welcome.png"]


def test_no_key_pauses(folder, monkeypatch):
    monkeypatch.delenv("SMART_EXPLORER_MOCK", raising=False)
    config.save(key="")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 120)
    assert fake.reads == [] and fake.said[-1] == watch.PROBLEMS["nokey"]


def test_test_mode_names_without_a_key(folder, monkeypatch):
    monkeypatch.setenv("SMART_EXPLORER_MOCK", "1")
    config.save(key="")
    w = watch.Watcher(clock=Clock(), say=lambda t: None)
    clock = w.clock
    run(w, clock, 120)
    assert files(folder) == ["Slide 1.png"]


def test_missing_folder_is_said_after_the_wait_and_grace(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=3, folder=str(folder.parent / "Gone")))
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 295)
    assert fake.said == ["Smart Explorer is watching Gone. New files will be renamed in 3 minutes."]
    assert watch.read_status()["message"] == "Waiting for Gone to appear"
    run(w, clock, 60)
    assert fake.said[-1] == "Smart Explorer can't find Gone. Check Google Drive is running and signed in."
    run(w, clock, 600)
    assert fake.said.count(fake.said[-1]) == 1


def test_folder_that_comes_back_resumes(folder):
    fake = Fake()
    w, clock = start(fake)
    hidden = folder.with_name("Sunday Media (signed out)")
    folder.rename(hidden)
    run(w, clock, 300)
    assert watch.PROBLEMS["folder"].format(folder="Sunday Media") in fake.said
    hidden.rename(folder)
    run(w, clock, 120)
    assert files(folder) == ["Name welcome.png"]


def test_free_check_reads_key_and_credit(monkeypatch):
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": False, "error": "x", "status": 401})
    assert watch.free_check("k") == "key"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": False, "error": "x", "status": 402})
    assert watch.free_check("k") == "credit"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": False, "error": "x", "status": None})
    assert watch.free_check("k") == "connection"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": True, "left": 0.0})
    assert watch.free_check("k") == "credit"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": True})
    monkeypatch.setattr(namer, "credits_left", lambda key: None)
    assert watch.free_check("k") is None
    monkeypatch.setattr(namer, "credits_left", lambda key: -0.01)
    assert watch.free_check("k") == "credit"
