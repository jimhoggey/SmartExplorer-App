import re
from collections import Counter
from pathlib import Path

IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
VIDEO = {".mp4", ".mov", ".m4v"}
PDF = {".pdf"}
EXTS = IMAGE | VIDEO | PDF


def kind(path):
    ext = Path(path).suffix.lower()
    return "video" if ext in VIDEO else "pdf" if ext in PDF else "image" if ext in IMAGE else None


def natural_key(path):
    """Sort 2.png before 10.png, the way Finder and Explorer do. Canva exports
    are numbered 1..N, so a plain string sort scrambles the slide order."""
    return [int(t) if t.isdecimal() else t for t in re.split(r"(\d+)", str(path).lower())]  # not isdigit: "²" is a digit but not a number


def _files(p):
    if p.is_dir():
        return [c for c in p.iterdir() if c.is_file()]
    return [p] if p.is_file() else []


def scan(*paths):
    """Supported files from any mix of folders (top level only) and single files,
    in natural order, each once."""
    seen, files = set(), []
    for p in paths:
        for f in _files(Path(p)):
            if kind(f) and not f.name.startswith(".") and f.resolve() not in seen:
                seen.add(f.resolve())
                files.append(f)
    files.sort(key=natural_key)
    return [{"id": i, "path": str(p), "name": p.name, "kind": kind(p)} for i, p in enumerate(files)]


def looks_numbered(items):
    """Whether files are numbered in sequence (1.png…14.png, Slide1…, Sermon.001…, or
    names that already start 01, 02…): renamed without numbers they would sort A to Z
    in ProPresenter, so Keep order is on for them. Every folder must be numbered, with
    small, distinct numbers: a deck (gaps allowed, for deleted slides), not a camera's
    IMG_4521. ASCII digits only, as in the window it came from."""
    if len(items) < 2:
        return False
    folders = {}
    for it in items:
        folders.setdefault(str(Path(it["path"]).parent), []).append(re.sub(r"\.[^.]+$", "", it["name"]))
    for stems in folders.values():
        lead = [re.match(r"([0-9]+)[\s._-]", s) for s in stems]
        tails = [re.sub(r"[0-9]+(?=[^0-9]*$)", "#", s, count=1) for s in stems]
        if all(lead):
            nums = [int(m.group(1)) for m in lead]
        elif all(t == tails[0] and "#" in t for t in tails):
            nums = [int(re.search(r"([0-9]+)[^0-9]*$", s).group(1)) for s in stems]
        else:
            return False
        if len(set(nums)) != len(nums) or max(nums) > 2 * len(nums):
            return False
    return True


def order_numbers(items):
    """Keep order's 01, 02… for each item: per folder, in list order, at least two digits."""
    folders = [str(Path(it["path"]).parent) for it in items]
    totals, seen, out = Counter(folders), Counter(), []
    for f in folders:
        seen[f] += 1
        out.append(str(seen[f]).zfill(max(2, len(str(totals[f])))))
    return out


def siblings(items, limit=500):
    """Names of the other files already in the items' folders, so new names can avoid them.
    Every file counts, whatever its type: ProPresenter shows names without extensions."""
    batch = {str(Path(i["path"])) for i in items}
    names = set()
    for folder in {Path(i["path"]).parent for i in items}:
        try:
            names.update(p.stem for p in folder.iterdir()
                         if p.is_file() and not p.name.startswith(".") and str(p) not in batch)
        except OSError:
            pass
    return sorted(names, key=str.lower)[:limit]
