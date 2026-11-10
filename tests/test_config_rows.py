import time

import config


def test_a_folder_list_from_0_7_becomes_rows_that_rename():
    config.save(watch={"enabled": True, "folders": ["/x/Sunday Media", "/x/Youth Media"]})
    s = config.watch_settings()
    assert s["rows"] == [
        {"path": "/x/Sunday Media", "name": "Sunday Media", "rename": True, "render": False, "output": "", "weekly": True},
        {"path": "/x/Youth Media", "name": "Youth Media", "rename": True, "render": False, "output": "", "weekly": True}]
    assert s["folders"] == ["/x/Sunday Media", "/x/Youth Media"] and s["loops"] == []
    config.save(watch={"folder": "C:\\Media\\Sunday\\"})
    assert config.watch_settings()["rows"][0]["name"] == "Sunday"


def test_rows_are_tidied_each_folder_once_and_at_most_ten():
    loop = {"path": ' "G:\\My Drive\\PreServiceLoop" ', "name": "  Pre-service loop ", "rename": False,
            "render": True, "output": "C:\\Loops"}
    config.save(watch={"rows": [loop, "g:/my drive/preserviceloop/", {"name": "no folder"}, 7, "/x/Sunday"]
                       + ["/x/%d" % i for i in range(20)]})
    s = config.watch_settings()
    assert s["rows"][0] == {"path": "G:\\My Drive\\PreServiceLoop", "name": "Pre-service loop", "rename": False,
                            "render": True, "output": "C:\\Loops", "weekly": True}
    assert [r["path"] for r in s["rows"]][:2] == ["G:\\My Drive\\PreServiceLoop", "/x/Sunday"]
    assert len(s["rows"]) == config.MAX_FOLDERS
    assert s["loops"] == [s["rows"][0]] and "G:\\My Drive\\PreServiceLoop" not in s["folders"]


def test_a_folder_changes_every_week_unless_unticked():
    config.save(watch={"rows": [{"path": "/x/a"}, {"path": "/x/b", "weekly": False}, {"path": "/x/c", "weekly": "no"}]})
    assert [r["weekly"] for r in config.watch_settings()["rows"]] == [True, False, True]


def test_the_week_starts_when_the_last_service_ended():
    times = [{"day": 6, "from": "08:00", "to": "15:00"}]  # Sunday
    sunday = lambda h, m=0, week=0: time.mktime((2026, 11, 8 + 7 * week, h, m, 0, 0, 0, -1))  # 8 Nov 2026 is a Sunday
    assert config.last_service_end(times, sunday(16)) == sunday(15)
    assert config.last_service_end(times, sunday(15)) == sunday(15)
    assert config.last_service_end(times, sunday(10)) == sunday(15, week=-1)  # during a service: the one before
    assert config.last_service_end(times, sunday(10) + 3 * 86400) == sunday(15)  # the Wednesday after
    assert config.last_service_end([], sunday(10)) is None
    friday = times + [{"day": 4, "from": "19:00", "to": "21:30"}]
    assert config.last_service_end(friday, sunday(10)) == time.mktime((2026, 11, 6, 21, 30, 0, 0, 0, -1))


def test_service_times_keep_only_times_that_start_before_they_end():
    config.save(watch={"service_times": [
        {"day": 6, "from": "8:00", "to": "15:00"},
        {"day": 4, "from": "19:00", "to": "18:00"},  # ends before it starts
        {"day": 7, "from": "08:00", "to": "09:00"},  # no such day
        {"day": True, "from": "08:00", "to": "09:00"},
        {"day": 0, "from": "25:00", "to": "26:00"},
        "Sunday"]})
    assert config.watch_settings()["service_times"] == [{"day": 6, "from": "08:00", "to": "15:00"}]


def test_service_until_says_when_the_service_time_ends():
    times = [{"day": 6, "from": "08:00", "to": "15:00"}]  # Sunday
    sunday = lambda h, m: time.mktime((2026, 11, 8, h, m, 0, 0, 0, -1))  # 8 Nov 2026 is a Sunday
    assert config.service_until(times, sunday(9, 30)) == sunday(15, 0)
    assert config.service_until(times, sunday(8, 0)) == sunday(15, 0)
    assert config.service_until(times, sunday(15, 0)) is None
    assert config.service_until(times, sunday(7, 59)) is None
    assert config.service_until(times, sunday(9, 30) + 86400) is None  # Monday
    assert config.service_until([], sunday(9, 30)) is None
