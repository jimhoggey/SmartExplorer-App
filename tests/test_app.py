import time

import pytest
from PIL import Image

import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setenv("SMART_EXPLORER_MOCK", "1")
    import app
    app.app.testing = True
    return app.app.test_client()


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "slides"
    d.mkdir()
    for n in ["b.png", "a.jpg"]:
        Image.new("RGB", (400, 200), "red").save(d / n)
    (d / "notes.txt").write_text("x")
    return d


def test_status_and_settings(client):
    s = client.get("/api/status").get_json()
    assert s["has_key"] is False and s["model"] == config.DEFAULT_MODEL
    assert s["models"][0]["id"] == config.DEFAULT_MODEL and s["models"][0]["note"]
    assert [p["id"] for p in s["profiles"]] == ["propresenter", "general"]
    assert all(p["description"] for p in s["profiles"])
    assert s["profile"] == "propresenter" and "rules" not in s
    assert "keep_order" not in s  # decided per batch in the window, never carried over
    assert s["spent_month"] == 0 and s["spent_total"] == 0
    assert s["version"] and s["version"].count(".") == 2
    s = client.post("/api/settings", json={"key": "sk", "model": "m", "rules": "We say Offering", "bogus": "x"}).get_json()
    assert s["has_key"] is True and s["model"] == "m"
    assert "bogus" not in config.load() and "rules" not in config.load()  # house rules were removed


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200 and b"<html" in r.data


def test_scan(client, folder):
    r = client.post("/api/scan", json={"folder": str(folder / "nope")})
    assert r.status_code == 400 and "Choose folder" in r.get_json()["error"]
    assert client.post("/api/scan", json={"folder": "."}).status_code == 400
    assert client.post("/api/scan", json={"paths": ["relative.png", 7]}).status_code == 400
    items = client.post("/api/scan", json={"folder": str(folder)}).get_json()["items"]
    assert [i["name"] for i in items] == ["a.jpg", "b.png"]
    assert all(i["thumb"] and i["kind"] == "image" for i in items)


def test_scan_says_whether_files_are_numbered(client, folder, tmp_path):
    assert client.post("/api/scan", json={"folder": str(folder)}).get_json()["numbered"] is False
    deck = tmp_path / "deck"
    deck.mkdir()
    for n in ("1.png", "2.png", "3.png"):
        Image.new("RGB", (40, 20), "blue").save(deck / n)
    assert client.post("/api/scan", json={"folder": str(deck)}).get_json()["numbered"] is True


def test_scan_dropped_files_and_folders(client, folder, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    Image.new("RGB", (40, 20), "blue").save(other / "c.png")
    items = client.post("/api/scan", json={"paths": [str(folder / "b.png"), str(other)]}).get_json()["items"]
    assert [i["name"] for i in items] == ["c.png", "b.png"]  # grouped by folder: other/ sorts before slides/


def _name(client, folder, **opts):
    job = client.post("/api/name", json=dict({"folder": str(folder)}, **opts)).get_json()["job"]
    for _ in range(100):
        r = client.get("/api/name/" + job).get_json()
        if r["done"]:
            return r
        time.sleep(0.05)
    raise AssertionError("job never finished")


def test_name_rename_undo(client, folder):
    r = _name(client, folder)
    assert r["results"][str(folder / "a.jpg")]["proposed"] == "Slide 1"
    assert r["results"][str(folder / "b.png")]["proposed"] == "Slide 2"
    assert r["cost"] == 0
    items = [{"path": str(folder / "a.jpg"), "new_name": "Slide 1"}, {"path": str(folder / "b.png"), "new_name": "b"}]
    r = client.post("/api/rename", json={"items": items}).get_json()
    assert r["renamed"] == 1 and (folder / "Slide 1.jpg").exists() and (folder / "b.png").exists()
    assert r["moved"] == [[str(folder / "a.jpg"), str(folder / "Slide 1.jpg")]]
    assert client.post("/api/undo", json={"journal": "../config"}).status_code == 404
    u = client.post("/api/undo", json={"journal": r["journal"]}).get_json()
    assert u == {"restored": 1, "moved": [[str(folder / "Slide 1.jpg"), str(folder / "a.jpg")]]}
    assert (folder / "a.jpg").exists()
    assert client.post("/api/undo", json={"journal": r["journal"]}).status_code == 404


def test_results_keyed_by_path_survive_a_file_landing_mid_flight(client, folder):
    """A file arriving between scan and name used to shift every result by one,
    so each card showed the right thumbnail beside its neighbour's name."""
    (folder / "0_new.png").write_bytes((folder / "a.jpg").read_bytes())
    r = _name(client, folder)
    # 0_new sorts first, so positional ids would hand a.jpg -> "Slide 2".
    assert r["results"][str(folder / "0_new.png")]["proposed"] == "Slide 1"
    assert r["results"][str(folder / "a.jpg")]["proposed"] == "Slide 2"
    # A card the browser holds but the server no longer sees simply has no entry.
    assert str(folder / "gone.png") not in r["results"]


def test_name_explicit_paths_with_options(client, folder):
    job = client.post("/api/name", json={"paths": [str(folder / "b.png")], "profile": "general"}).get_json()["job"]
    for _ in range(100):
        r = client.get("/api/name/" + job).get_json()
        if r["done"]:
            break
        time.sleep(0.05)
    # Keep order's 01, 02… are added in the window (outside the editable name), not here.
    assert r["results"] == {str(folder / "b.png"): {"proposed": "Slide 1", "error": None}}
    assert client.get("/api/status").get_json()["profile"] == "general"  # remembered for next launch


def test_spend_adds_up_per_month(client, folder, monkeypatch):
    """Each batch's cost is kept, so Settings can say what naming has cost this month and in all."""
    import app
    import namer
    monkeypatch.setattr(namer, "mock_run", lambda items, *a, **k: {
        "results": [{"id": i["id"], "path": i["path"], "proposed": "X"} for i in items], "cost": 0.0125})
    config.save(spend={"2026-01": 1.5, "bad": "x"})
    _name(client, folder)
    _name(client, folder)
    s = client.get("/api/status").get_json()
    assert s["spent_month"] == pytest.approx(0.025) and s["spent_total"] == pytest.approx(1.525)
    app.record_spend(0)  # a batch that cost nothing leaves the file alone
    assert config.load()["spend"][time.strftime("%Y-%m")] == pytest.approx(0.025)


def test_prompts_view_edit_and_reset(client):
    import namer
    styles = client.get("/api/prompts").get_json()["profiles"]
    pp = styles[0]
    assert pp["id"] == "propresenter" and pp["label"] == "ProPresenter" and pp["description"]
    assert pp["current"] == pp["defaults"] and pp["edited"] == []
    assert styles[1]["label"] == "Photos & files" and "date" in styles[1]["description"]
    rules = pp["defaults"]["rules"].replace("Giving", "Offering")
    pp = client.post("/api/prompts", json={"profile": "propresenter", "rules": rules,
                                           "reader": pp["defaults"]["reader"], "categories": ""}).get_json()["profiles"][0]
    assert pp["edited"] == ["rules"] and pp["current"]["rules"] == rules
    assert config.load()["prompt_edits"] == {"propresenter": {"rules": rules}}  # only what differs is kept
    assert "Offering" in namer.name_prompt("propresenter")
    client.post("/api/prompts", json={"profile": "propresenter", "rules": "  "})  # emptied: back to the default
    assert client.get("/api/prompts").get_json()["profiles"][0]["edited"] == []
    assert config.load()["prompt_edits"] == {}


def test_saving_one_part_keeps_the_others(client):
    client.post("/api/prompts", json={"profile": "general", "reader": "Look closely.", "rules": "Name by {categories}"})
    client.post("/api/prompts", json={"profile": "general", "rules": ""})  # only rules sent, emptied
    assert config.load()["prompt_edits"] == {"general": {"reader": "Look closely."}}


def test_prompts_reject_bad_input(client):
    assert client.post("/api/prompts", json={"profile": "../x", "rules": "a"}).status_code == 400
    r = client.post("/api/prompts", json={"profile": "general", "rules": "x" * 20001})
    assert r.status_code == 400 and "too long" in r.get_json()["error"]


def test_prompt_preview(client):
    r = client.post("/api/prompts/preview", json={"profile": "general", "rules": "Call everything {categories}",
                                                  "categories": "Thing"}).get_json()
    assert "Call everything Thing" in r["name"] and "Thing" in r["read"]
    assert '"names"' in r["name"] and '"files"' in r["read"]  # the reply format stays the app's own
    assert "prompt_edits" not in config.load()


def test_name_unknown_profile_falls_back(client, folder):
    _name(client, folder, profile="../../etc")
    assert config.load()["profile"] == "propresenter"


def test_name_requires_key(client, folder, monkeypatch):
    monkeypatch.delenv("SMART_EXPLORER_MOCK")
    r = client.post("/api/name", json={"folder": str(folder)})
    assert r.status_code == 400 and "Settings" in r.get_json()["error"]


def test_pick_folder_without_window(client):
    assert client.get("/api/pick-folder").get_json() == {"folder": None}


def test_name_tells_the_namer_what_is_already_in_the_folder(client, folder, monkeypatch):
    import namer
    seen = {}

    def run(key, model, items, encode, on_progress=None, **opts):
        seen.update(opts, names=[i["name"] for i in items])
        return {"results": [{"id": i["id"], "path": i["path"], "proposed": "X"} for i in items], "cost": 0.0}

    monkeypatch.setattr(namer, "run", run)
    config.save(key="sk-or-test")
    (folder / "Giving.png").write_bytes((folder / "a.jpg").read_bytes())
    job = client.post("/api/name", json={"paths": [str(folder / "b.png")]}).get_json()["job"]
    for _ in range(100):
        if client.get("/api/name/" + job).get_json()["done"]:
            break
        time.sleep(0.05)
    assert seen["names"] == ["b.png"]
    assert seen["existing"] == ["a", "Giving", "notes"]


def test_update_endpoints(client, monkeypatch):
    import updater
    asked = []
    monkeypatch.setattr(updater, "check", lambda force=False: asked.append(force) or {"current": "0.3.0", "latest": "0.4.0", "newer": True})
    monkeypatch.setattr(updater, "STATE", {"state": "idle", "done": 0, "total": 0, "error": None})
    r = client.get("/api/update").get_json()
    assert r["newer"] and r["progress"]["state"] == "idle"
    client.get("/api/update?force=1")
    assert asked == [False, True]
    monkeypatch.setattr(updater, "start", lambda: "There is no update to install.")
    r = client.post("/api/update")
    assert r.status_code == 400 and "no update" in r.get_json()["error"]
    monkeypatch.setattr(updater, "start", lambda: None)
    assert client.post("/api/update").get_json()["progress"]["state"] == "idle"


@pytest.fixture
def watcher(monkeypatch):
    import autostart
    import watch
    calls = {"spawn": 0, "stop": 0, "running": False, "auto": []}
    monkeypatch.setattr(watch, "running", lambda: calls["running"])
    monkeypatch.setattr(watch, "spawn", lambda: calls.__setitem__("spawn", calls["spawn"] + 1))
    monkeypatch.setattr(watch, "request_stop", lambda: calls.__setitem__("stop", calls["stop"] + 1))
    monkeypatch.setattr(autostart, "available", lambda system=None: True)
    monkeypatch.setattr(autostart, "enabled", lambda: False)
    monkeypatch.setattr(autostart, "enable", lambda: calls["auto"].append("on"))
    monkeypatch.setattr(autostart, "disable", lambda: calls["auto"].append("off"))
    return calls


def test_watch_starts_off(client, watcher):
    w = client.get("/api/watch").get_json()
    assert w["settings"] == config.WATCH_DEFAULTS and w["running"] is False and w["spent_month"] == 0
    assert w["can_autostart"] is True and w["status"] == {} and w["autostart_on"] is False


def test_a_start_up_item_is_checked_after_adding_it(client, watcher, folder, monkeypatch):
    import autostart
    there = {"on": False}
    monkeypatch.setattr(autostart, "enable", lambda: None)  # said it worked…
    monkeypatch.setattr(autostart, "enabled", lambda: there["on"])  # …but nothing is there
    w = client.post("/api/watch", json={"enabled": True, "folder": str(folder), "autostart": True}).get_json()
    assert "start-up items" in w["error"] and w["autostart_on"] is False
    there["on"] = True
    w = client.post("/api/watch", json={"monthly_limit_usd": 6}).get_json()
    assert "error" not in w and w["autostart_on"] is True


def test_start_up_items_can_be_shown(client, watcher, monkeypatch):
    import autostart
    shown = []
    monkeypatch.setattr(autostart, "show", lambda: shown.append(1))
    assert client.post("/api/watch/startup-items", json={}).status_code == 200 and shown == [1]


def test_watch_preview_counts_what_would_be_left_alone(client, watcher, folder):
    assert client.post("/api/watch/preview", json={"folder": str(folder)}).get_json() == {"count": 2}
    assert client.post("/api/watch/preview", json={"folder": "relative"}).status_code == 400


def test_turning_watching_on_records_the_folder_and_starts(client, watcher, folder):
    import known
    w = client.post("/api/watch", json={"enabled": True, "folder": str(folder), "startup_wait_min": 5,
                                        "monthly_limit_usd": 8, "autostart": True}).get_json()
    assert w["settings"]["enabled"] is True and w["settings"]["startup_wait_min"] == 5
    assert known.new_files(folder) == []  # what was there is left alone
    assert watcher["spawn"] == 1 and watcher["auto"] == ["on"]
    watcher["running"] = True
    client.post("/api/watch", json={"monthly_limit_usd": 9})
    assert watcher["spawn"] == 1  # already running
    client.post("/api/watch", json={"enabled": False})
    assert watcher["stop"] == 1 and watcher["auto"][-1] == "off"


def test_a_just_started_watcher_says_starting(client, watcher, folder):
    w = client.post("/api/watch", json={"enabled": True, "folder": str(folder)}).get_json()
    assert w["running"] is False and w["starting"] is True  # the new process needs a moment
    assert client.get("/api/watch").get_json()["starting"] is True


def test_a_folder_that_cannot_be_opened_is_refused(client, watcher, folder, monkeypatch):
    import known

    def denied(f):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(known, "visible", denied)
    r = client.post("/api/watch/preview", json={"folder": str(folder)})
    assert r.status_code == 400 and "open" in r.get_json()["error"]
    r = client.post("/api/watch", json={"enabled": True, "folder": str(folder)})
    assert r.status_code == 400 and not config.watch_settings()["enabled"] and watcher["spawn"] == 0


def test_watching_a_missing_folder_is_refused(client, watcher, tmp_path):
    r = client.post("/api/watch", json={"enabled": True, "folder": str(tmp_path / "nope")})
    assert r.status_code == 400 and not config.watch_settings()["enabled"]


def test_start_button_starts_a_stopped_watcher(client, watcher, folder):
    client.post("/api/watch/start", json={})
    assert watcher["spawn"] == 0  # watching is off
    client.post("/api/watch", json={"enabled": True, "folder": str(folder)})
    client.post("/api/watch/start", json={})
    assert watcher["spawn"] == 2


def test_spend_totals_include_background_renaming(client, watcher):
    import watch
    watch.record_spend(0.4)
    s = client.get("/api/status").get_json()
    assert s["spent_month"] == pytest.approx(0.4) and s["spent_total"] == pytest.approx(0.4)
    assert client.get("/api/watch").get_json()["spent_month"] == pytest.approx(0.4)


def test_window_renames_in_the_watched_folder_become_known(client, watcher, folder):
    import known
    client.post("/api/watch", json={"enabled": True, "folder": str(folder)})
    Image.new("RGB", (40, 20), "green").save(folder / "c.png")
    client.post("/api/rename", json={"items": [{"path": str(folder / "c.png"), "new_name": "Giving"}]})
    assert known.new_files(folder) == []
