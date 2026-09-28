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
    assert s["profile"] == "propresenter" and s["keep_order"] is False and "rules" not in s
    s = client.post("/api/settings", json={"key": "sk", "model": "m", "rules": "We say Offering", "bogus": "x"}).get_json()
    assert s["has_key"] is True and s["model"] == "m"
    assert "bogus" not in config.load() and "rules" not in config.load()  # house rules were removed


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200 and b"<html" in r.data


def test_scan(client, folder):
    assert client.post("/api/scan", json={"folder": str(folder / "nope")}).status_code == 400
    assert client.post("/api/scan", json={"folder": "."}).status_code == 400
    assert client.post("/api/scan", json={"paths": ["relative.png", 7]}).status_code == 400
    items = client.post("/api/scan", json={"folder": str(folder)}).get_json()["items"]
    assert [i["name"] for i in items] == ["a.jpg", "b.png"]
    assert all(i["thumb"] and i["kind"] == "image" for i in items)


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
    job = client.post("/api/name", json={"paths": [str(folder / "b.png")], "profile": "general", "keep_order": True}).get_json()["job"]
    for _ in range(100):
        r = client.get("/api/name/" + job).get_json()
        if r["done"]:
            break
        time.sleep(0.05)
    assert r["results"] == {str(folder / "b.png"): {"proposed": "01 Slide 1", "error": None}}
    s = client.get("/api/status").get_json()
    assert s["profile"] == "general" and s["keep_order"] is True  # remembered for next launch


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
