import re
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
