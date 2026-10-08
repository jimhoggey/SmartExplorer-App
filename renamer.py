import errno
import json
import os
import re
import uuid
from pathlib import Path

import config

BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(1, 10)), *("LPT%d" % i for i in range(1, 10))}


def sanitize(name, ext):
    name = re.sub(r"(?<=\d):(?=\d)", ".", name)  # John 3:16 -> John 3.16, not "John 3 16"
    name = re.sub(r"\s+", " ", BAD.sub(" ", name)).strip()[:100].rstrip(" .")
    if name.split(".")[0].rstrip().upper() in RESERVED:
        name = "_" + name
    return (name or "Untitled") + ext


def plan(items):
    taken, out = set(), []
    for it in items:
        old = Path(it["path"])
        stem = sanitize(it["new_name"], "")
        n, new = 1, stem + old.suffix
        if new == old.name or not old.is_file():
            continue
        while (old.parent, new.lower()) in taken or (old.with_name(new).exists() and not old.with_name(new).samefile(old)):
            n += 1
            new = "%s (%d)%s" % (stem, n, old.suffix)
        taken.add((old.parent, new.lower()))
        out.append((str(old), str(old.with_name(new))))
    return out


def apply(pairs, journal_dir=None):
    journal_dir = Path(journal_dir or config.CONFIG_DIR / "journal")
    journal_dir.mkdir(parents=True, exist_ok=True)
    out = {"journal": uuid.uuid4().hex, "renamed": 0}
    for old, new in pairs:
        try:
            # os.rename silently replaces an existing file on macOS and Linux.
            if os.path.exists(new) and not os.path.samefile(old, new):
                raise FileExistsError(errno.EEXIST, "a file with that name appeared since the names were checked")
            os.rename(old, new)
        except OSError as e:
            out["error"] = "Could not rename %s: %s" % (Path(old).name, e.strerror or e)
            break
        out["renamed"] += 1
    try:
        (journal_dir / (out["journal"] + ".json")).write_text(json.dumps(pairs[:out["renamed"]]), "utf-8")
    except OSError as e:  # the files are renamed already: say so, rather than lose track of them
        msg = "The undo record could not be saved: %s" % (e.strerror or e)
        out["error"] = "%s. %s" % (out["error"], msg) if "error" in out else msg
    return out


def undo(journal_id, journal_dir=None):
    """Reverse a batch. Returns the [current, restored] path pairs it moved."""
    path = Path(journal_dir or config.CONFIG_DIR / "journal") / (journal_id + ".json")
    moved = []
    for old, new in reversed(json.loads(path.read_text("utf-8"))):
        if os.path.exists(new) and (not os.path.exists(old) or os.path.samefile(old, new)):
            os.rename(new, old)
            moved.append([new, old])
    path.unlink()
    return moved
