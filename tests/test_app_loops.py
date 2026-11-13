import json

import pytest
from PIL import Image

import config
import known
from test_app import client, watcher  # noqa: F401  (fixtures)


@pytest.fixture
def loop(tmp_path):
    src = tmp_path / "PreServiceLoop"
    src.mkdir()
    for i in (1, 2):
        Image.new("RGB", (40, 20), "teal").save(src / ("%d.png" % i))
    (src / "notes.pdf").write_bytes(b"%PDF")
    out = tmp_path / "ProPresenter Loops"
    out.mkdir()
    return {"path": str(src), "name": "Pre-service loop", "rename": False, "render": True, "output": str(out)}


def save(client, rows, **kw):
    return client.post("/api/watch", json=dict({"enabled": True, "rows": rows}, **kw))


def test_a_loop_row_is_saved_with_its_service_times(client, watcher, loop, tmp_path):
    media = tmp_path / "Sunday Media"
    media.mkdir()
    times = [{"day": 6, "from": "08:00", "to": "15:00"}]
    w = save(client, [loop, str(media)], service_times=times).get_json()
    assert w["settings"]["loops"] == [dict(loop, weekly=True, move_to="")] and w["settings"]["folders"] == [str(media)]
    assert w["sunday"]["state"] != "off"  # watching: the start screen's Sunday check has something to say
    assert w["settings"]["service_times"] == times and watcher["spawn"] == 1
    assert w["loops"] == {config.folder_key(loop["path"]): {"state": "none", "text": "Not rendered yet"}}
    saved = config.load()["watch"]
    assert saved["folders"] == [str(media)]  # what 0.7 reads, should it come back
    assert known.has_record(media) and not known.has_record(loop["path"])  # a loop's files aren't renamed


@pytest.mark.parametrize("change, message", [
    ({"render": False, "rename": False}, "Tick Rename new files or Render into video for Pre-service loop, or remove it."),
    ({"output": ""}, "Choose where to save Pre-service loop's video."),
    ({"name": "Pre:service"}, 'A video can\'t be called "Pre:service". Use letters, numbers, spaces and dashes.'),
    ({"name": "CON"}, 'A video can\'t be called "CON". Use letters, numbers, spaces and dashes.'),
    ({"name": "Loop."}, 'A video can\'t be called "Loop.". Use letters, numbers, spaces and dashes.'),
    ({"output": "missing"}, "Can't save into missing. Check the folder is there and can be written to."),
])
def test_save_refuses_a_loop_it_cant_make_and_names_the_row(client, watcher, loop, tmp_path, change, message):
    if change.get("output") == "missing":
        change = {"output": str(tmp_path / "missing")}
    r = save(client, [dict(loop, **change)])
    assert r.status_code == 400
    assert r.get_json() == {"error": message, "folder": loop["path"]}
    assert config.watch_settings()["rows"] == [] and watcher["spawn"] == 0


def test_a_video_can_not_be_saved_inside_a_watched_folder(client, watcher, loop, tmp_path):
    r = save(client, [dict(loop, output=loop["path"])])
    assert "outside the folders Smart Explorer watches" in r.get_json()["error"]
    media = tmp_path / "Sunday Media"
    (media / "Loops").mkdir(parents=True)
    r = save(client, [dict(loop, output=str(media / "Loops")), str(media)])
    assert r.status_code == 400 and r.get_json()["folder"] == loop["path"]


def test_two_loops_can_not_save_the_same_video(client, watcher, loop, tmp_path):
    post = tmp_path / "EndServiceLoop"
    post.mkdir()
    r = save(client, [loop, dict(loop, path=str(post))])
    assert r.get_json() == {"error": "PreServiceLoop and EndServiceLoop would both save Pre-service loop.mp4 in "
                                     "ProPresenter Loops. Give one another name.", "folder": str(post)}
    assert save(client, [loop, dict(loop, path=str(post), name="Post-service loop")]).status_code == 200


def test_with_watching_off_the_table_is_saved_without_looking_on_disk(client, watcher, loop, tmp_path):
    r = save(client, [dict(loop, output=str(tmp_path / "not yet"))], enabled=False)
    assert r.status_code == 200 and config.watch_settings()["loops"][0]["output"] == str(tmp_path / "not yet")
    assert save(client, [dict(loop, render=False, rename=False)], enabled=False).status_code == 400


def test_ticking_rename_on_a_loop_folder_leaves_its_files_as_they_are(client, watcher, loop):
    save(client, [loop])
    assert not known.has_record(loop["path"])
    save(client, [dict(loop, rename=True)])
    assert known.has_record(loop["path"])


def test_preview_says_what_a_loop_would_hold_and_whether_its_video_is_there(client, watcher, loop):
    r = client.post("/api/watch/preview", json={"rows": [loop]}).get_json()
    assert r == {"counts": {loop["path"]: 3}, "loops": {loop["path"]: {"screens": 2, "exists": False}}}
    (config.Path(loop["output"]) / "Pre-service loop.mp4").write_bytes(b"old")
    r = client.post("/api/watch/preview", json={"rows": [loop]}).get_json()
    assert r["loops"][loop["path"]]["exists"] is True


def test_more_than_ten_rows_are_refused_not_dropped(client, watcher, tmp_path):
    rows = [{"path": str(tmp_path / str(i)), "render": False} for i in range(11)]
    r = save(client, rows)
    assert r.status_code == 400 and "up to 10" in r.get_json()["error"]


def test_render_now_asks_the_background_copy(client, watcher, loop, tmp_path):
    r = client.post("/api/loops/render", json={"path": loop["path"]})
    assert r.status_code == 400  # not saved as a loop yet
    save(client, [loop], enabled=False)
    assert client.post("/api/loops/render", json={"path": loop["path"]}).status_code == 409
    save(client, [loop])
    spawned = watcher["spawn"]
    r = client.post("/api/loops/render", json={"path": loop["path"] + "/", "anyway": True})
    assert r.status_code == 200 and watcher["spawn"] == spawned + 1
    asked = json.loads((config.CONFIG_DIR / "watch" / "render.json").read_text("utf-8"))
    assert asked == [{"path": loop["path"] + "/", "anyway": True}]
