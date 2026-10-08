import os

import pytest
from PIL import Image

import known


SIZES = iter(range(20, 2000))


def png(path, color="red"):
    """A distinct image each time: same-sized files made in the same second would share a print."""
    Image.new("RGB", (next(SIZES), 36), color).save(path)


def names(pairs):
    return [p.name for p, _ in pairs]


def test_recorded_files_are_not_new_but_later_ones_are(tmp_path):
    png(tmp_path / "old.png")
    assert known.record_folder(tmp_path) == 1
    assert known.new_files(tmp_path) == []
    png(tmp_path / "10.png")
    png(tmp_path / "2.png", "blue")
    assert names(known.new_files(tmp_path)) == ["2.png", "10.png"]


def test_hand_renamed_and_replaced_files_are_not_new(tmp_path):
    png(tmp_path / "a.png")
    png(tmp_path / "b.png")
    known.record_folder(tmp_path)
    os.rename(tmp_path / "a.png", tmp_path / "Renamed by hand.png")  # same print
    png(tmp_path / "b.png", "green")  # an updated slide under the same name
    os.utime(tmp_path / "b.png", (1, 1))
    assert known.new_files(tmp_path) == []


def test_only_files_it_would_name_count(tmp_path):
    for n in (".hidden.png", "~$lock.png", "notes.txt", "download.tmp"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    png(tmp_path / "sub" / "deep.png")
    assert known.visible(tmp_path) == [] and known.new_files(tmp_path) == []
    assert known.record_folder(tmp_path) == 0


def test_add_and_add_paths(tmp_path):
    known.record_folder(tmp_path)
    png(tmp_path / "a.png")
    png(tmp_path / "b.png", "blue")
    known.add(tmp_path, [("A.PNG", "0:0")])  # names match whatever the case
    assert names(known.new_files(tmp_path)) == ["b.png"]
    other = tmp_path / "other"
    other.mkdir()
    png(other / "c.png")
    known.add_paths(tmp_path, [tmp_path / "b.png", other / "c.png", tmp_path / "gone.png"])
    assert known.new_files(tmp_path) == []


def test_folders_are_kept_apart_and_a_missing_folder_is_empty(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    png(a / "x.png")
    png(b / "x.png")
    known.record_folder(a)
    assert known.new_files(a) == [] and names(known.new_files(b)) == ["x.png"]
    assert known.has_record(a) and not known.has_record(b)
    with pytest.raises(OSError):  # a folder that can't be listed is not an empty one
        known.new_files(tmp_path / "missing")


def test_forget_names_keeps_prints(tmp_path):
    png(tmp_path / "1.png")
    known.record_folder(tmp_path)
    assert known.names(tmp_path) == {"1.png"}
    known.forget_names(tmp_path, {"1.png"})
    assert known.names(tmp_path) == set()
    assert known.new_files(tmp_path) == []  # still known by its print


def test_same_folder(tmp_path):
    assert known.same_folder(tmp_path, str(tmp_path) + os.sep)
    assert known.same_folder(tmp_path / "x" / "..", tmp_path)
    assert not known.same_folder(tmp_path, tmp_path / "x")
    assert not known.same_folder("", tmp_path)


def test_damaged_record_starts_afresh(tmp_path):
    png(tmp_path / "a.png")
    path = known._path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken")
    assert names(known.new_files(tmp_path)) == ["a.png"]
    known.record_folder(tmp_path)
    assert known.new_files(tmp_path) == []
