import json
import os
from pathlib import Path

import pytest

import config
import renamer
import scanner


def test_scan(tmp_path):
    for n in ["b.PNG", "a.mp4", "c.txt", "d.pdf", "e.HEIC", "._e.HEIC"]:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.png").write_bytes(b"x")
    items = scanner.scan(str(tmp_path))
    assert [(i["name"], i["kind"], i["id"]) for i in items] == [
        ("a.mp4", "video", 0), ("b.PNG", "image", 1), ("d.pdf", "pdf", 2), ("e.HEIC", "image", 3)]
    assert items[0]["path"] == str(tmp_path / "a.mp4")


def test_scan_sorts_canva_exports_naturally(tmp_path):
    for n in ["10.png", "2.png", "1.png", "Deck - 11.png", "Deck - 9.png"]:
        (tmp_path / n).write_bytes(b"x")
    assert [i["name"] for i in scanner.scan(str(tmp_path))] == ["1.png", "2.png", "10.png", "Deck - 9.png", "Deck - 11.png"]


def test_scan_mixes_folders_and_files_once_each(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for p in [a / "1.png", a / "2.png", b / "x.jpg", b / "notes.txt"]:
        p.write_bytes(b"x")
    items = scanner.scan(str(a), str(a / "2.png"), str(b / "x.jpg"), str(b / "notes.txt"), str(tmp_path / "gone.png"))
    assert [i["path"] for i in items] == [str(a / "1.png"), str(a / "2.png"), str(b / "x.jpg")]
    assert [i["id"] for i in items] == [0, 1, 2]


def test_config_model_falls_back_from_retired(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    assert config.model() == config.DEFAULT_MODEL
    config.save(model="google/gemini-2.5-flash")  # being retired by Google
    assert config.model() == config.DEFAULT_MODEL
    config.save(model="someone/custom-model")
    assert config.model() == "someone/custom-model"


def test_config_roundtrip_and_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    assert config.load() == {}
    assert config.save(key="k") == {"key": "k"}
    assert config.load()["key"] == "k"
    assert config.save(model="m") == {"key": "k", "model": "m"}
    (tmp_path / "cfg" / "config.json").write_text("{not json")
    assert config.load() == {}


def test_sanitize():
    assert renamer.sanitize("Giving: Full/Details?", ".png") == "Giving Full Details.png"
    assert renamer.sanitize("  \x01 ", ".png") == "Untitled.png"
    assert renamer.sanitize("a" * 200, ".png") == "a" * 100 + ".png"
    assert renamer.sanitize("con", ".png") == "_con.png"
    assert renamer.sanitize("Aux. Details", ".png") == "_Aux. Details.png"
    assert renamer.sanitize("Scripture - John 3:16", ".png") == "Scripture - John 3.16.png"


def test_plan_collisions_and_unchanged(tmp_path):
    (tmp_path / "Giving.png").write_bytes(b"x")
    for n in ["one.png", "two.png", "same.png"]:
        (tmp_path / n).write_bytes(b"x")
    items = [
        {"path": str(tmp_path / "one.png"), "new_name": "Giving"},
        {"path": str(tmp_path / "two.png"), "new_name": "Giving"},
        {"path": str(tmp_path / "same.png"), "new_name": "same"},
    ]
    assert renamer.plan(items) == [
        (str(tmp_path / "one.png"), str(tmp_path / "Giving (2).png")),
        (str(tmp_path / "two.png"), str(tmp_path / "Giving (3).png")),
    ]


def test_plan_collisions_are_per_folder(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    one, two = tmp_path / "a" / "1.png", tmp_path / "b" / "1.png"
    one.write_bytes(b"x")
    two.write_bytes(b"x")
    items = [{"path": str(one), "new_name": "Giving"}, {"path": str(two), "new_name": "Giving"}]
    assert [Path(new).name for _, new in renamer.plan(items)] == ["Giving.png", "Giving.png"]


def test_apply_never_overwrites_a_file_that_appeared(tmp_path):
    a = tmp_path / "a.png"
    a.write_bytes(b"a")
    (tmp_path / "x.png").write_bytes(b"precious")
    r = renamer.apply([(str(a), str(tmp_path / "x.png"))], tmp_path / "journal")
    assert r["renamed"] == 0 and "a.png" in r["error"]
    assert (tmp_path / "x.png").read_bytes() == b"precious" and a.exists()


def test_apply_and_undo(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    journal = tmp_path / "journal"
    pairs = [(str(a), str(tmp_path / "x.png")), (str(b), str(tmp_path / "y.png"))]
    jid = renamer.apply(pairs, journal)["journal"]
    assert not a.exists() and (tmp_path / "x.png").read_bytes() == b"a"
    assert json.loads((journal / (jid + ".json")).read_text()) == [list(p) for p in pairs]
    assert renamer.undo(jid, journal) == [[str(tmp_path / "y.png"), str(b)], [str(tmp_path / "x.png"), str(a)]]
    assert a.read_bytes() == b"a" and b.read_bytes() == b"b"
    assert not (journal / (jid + ".json")).exists()


def test_apply_partial_failure_is_journaled(tmp_path):
    a = tmp_path / "a.png"
    a.write_bytes(b"a")
    pairs = [(str(a), str(tmp_path / "x.png")), (str(tmp_path / "missing.png"), str(tmp_path / "y.png"))]
    r = renamer.apply(pairs, tmp_path / "journal")
    assert r["renamed"] == 1 and "missing.png" in r["error"]
    assert len(renamer.undo(r["journal"], tmp_path / "journal")) == 1 and a.exists()


def test_plan_skips_missing_files(tmp_path):
    assert renamer.plan([{"path": str(tmp_path / "nope.png"), "new_name": "x"}]) == []


def test_scan_survives_unicode_digits(tmp_path):
    for n in ["Room 1²3.png", "Room 2.png"]:
        (tmp_path / n).write_bytes(b"x")
    assert [i["name"] for i in scanner.scan(str(tmp_path))] == ["Room 1²3.png", "Room 2.png"]


def test_siblings_lists_other_files_in_the_batch_folders(tmp_path):
    for n in ["1.png", "2.png", "Giving.png", "Giving.pdf", "notes.txt", ".DS_Store"]:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    batch = [i for i in scanner.scan(str(tmp_path)) if i["name"] in ("1.png", "2.png")]
    assert scanner.siblings(batch) == ["Giving", "notes"]


def test_save_writes_atomically_and_leaves_no_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    swaps = []
    real = os.replace
    monkeypatch.setattr(config.os, "replace", lambda a, b: (swaps.append((Path(a).name, Path(b).name)), real(a, b)))
    config.save(key="sk")
    assert config.load()["key"] == "sk"
    assert swaps and swaps[0][1] == "config.json" and swaps[0][0].endswith(".tmp")
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_write_json_retries_while_the_file_is_busy(tmp_path, monkeypatch):
    calls = []
    real = os.replace

    def busy_once(a, b):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("in use")  # Windows: another process is reading it
        real(a, b)

    monkeypatch.setattr(config.os, "replace", busy_once)
    monkeypatch.setattr(config.time, "sleep", lambda s: None)
    config.write_json(tmp_path / "x.json", {"a": 1})
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": 1} and len(calls) == 2


def test_watch_settings_defaults_and_clamps(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assert config.watch_settings() == config.WATCH_DEFAULTS
    config.save(watch={"enabled": "yes", "folder": 7, "startup_wait_min": 99, "monthly_limit_usd": -3, "autostart": True})
    s = config.watch_settings()
    assert s["enabled"] is False and s["folder"] == "" and s["autostart"] is True
    assert s["startup_wait_min"] == 30 and s["monthly_limit_usd"] == 0.0
    config.save(watch={"enabled": True, "folder": "/x", "startup_wait_min": True, "monthly_limit_usd": 12.5})
    s = config.watch_settings()
    assert s["enabled"] is True and s["folder"] == "/x" and s["startup_wait_min"] == 3 and s["monthly_limit_usd"] == 12.5
    (tmp_path / "config.json").write_text("{broken")
    assert config.watch_settings() == config.WATCH_DEFAULTS
    config.save(watch="nonsense")
    assert config.watch_settings() == config.WATCH_DEFAULTS
