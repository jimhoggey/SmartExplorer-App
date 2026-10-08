"""The files Smart Explorer already knows in a watched folder, so background
renaming only ever touches new ones.

For every known file it keeps the name (lower case) and a print: size and modified
time in whole seconds. A file is new only when both are unknown: a file someone
renamed by hand keeps its print, and an updated slide uploaded under the same name
keeps its name, so neither is renamed again. Kept in ~/.smart-explorer/watch/known.json,
one entry per folder.
"""
import json
import os
from pathlib import Path

import config
import scanner


def _path():
    return config.CONFIG_DIR / "watch" / "known.json"


def _key(folder):
    return os.path.normcase(os.path.abspath(str(folder)))


def same_folder(a, b):
    return bool(str(a or "")) and bool(str(b or "")) and _key(a) == _key(b)


def fingerprint(path):
    st = os.stat(path)
    return "%d:%d" % (st.st_size, int(st.st_mtime))


def _load():
    try:
        data = json.loads(_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _entry(data, folder):
    e = data.get(_key(folder))
    e = e if isinstance(e, dict) else {}
    return ({n for n in e.get("names", []) if isinstance(n, str)},
            {f for f in e.get("prints", []) if isinstance(f, str)})


def _save(data, folder, names, prints):
    data[_key(folder)] = {"names": sorted(names), "prints": sorted(prints)}
    config.write_json(_path(), data)


def visible(folder):
    """The files background renaming would name: the folder's top level only, no
    hidden files, no Office or Google Drive temporary files, only types it reads."""
    try:
        files = [p for p in Path(folder).iterdir() if p.is_file()]
    except OSError:
        return []
    return sorted((p for p in files if scanner.kind(p) and not p.name.startswith((".", "~$"))), key=scanner.natural_key)


def _prints(paths):
    out = []
    for p in paths:
        try:
            out.append((p.name, fingerprint(p)))
        except OSError:  # gone since the folder was listed
            pass
    return out


def record_folder(folder):
    """Know every file in the folder now, so watching leaves them as they are.
    Returns how many there are."""
    files = visible(folder)
    entries = _prints(files)
    _save(_load(), folder, {n.lower() for n, _ in entries}, {f for _, f in entries})
    return len(files)


def add(folder, entries):
    """Know these (name, print) pairs too."""
    entries = list(entries)
    if not entries:
        return
    data = _load()
    names, prints = _entry(data, folder)
    _save(data, folder, names | {n.lower() for n, _ in entries}, prints | {f for _, f in entries})


def add_paths(folder, paths):
    """Know these files, the ones that are in the folder (renamed in the window, say)."""
    add(folder, _prints([Path(p) for p in paths if same_folder(Path(p).parent, folder)]))


def new_files(folder):
    """The folder's new files as [(path, print)], in natural order."""
    names, prints = _entry(_load(), folder)
    return [(p, f) for p in visible(folder) for n, f in _prints([p]) if n.lower() not in names and f not in prints]
