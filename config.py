import datetime
import json
import os
import re
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".smart-explorer"

# OpenRouter model ids, best first. Per-file costs are rough estimates from
# OpenRouter's September 2026 prices; the app shows the real cost of each batch.
MODELS = [
    {"id": "anthropic/claude-sonnet-5", "label": "Claude Sonnet 5 (recommended)",
     "note": "Most accurate text reading. Around half a cent a file."},
    {"id": "google/gemini-3.8-flash", "label": "Gemini 3.8 Flash",
     "note": "Faster, around a fifth of a cent a file."},
    {"id": "google/gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite",
     "note": "Cheapest, well under a tenth of a cent a file. For big batches of simple files."},
]
DEFAULT_MODEL = MODELS[0]["id"]
# Being retired by Google (published shutdown dates have moved around October 2026);
# a saved choice of one of these falls back to the default.
RETIRED = {"google/gemini-2.5-flash", "google/gemini-2.5-flash-lite"}


def load():
    try:
        return json.loads((CONFIG_DIR / "config.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def model():
    m = load().get("model")
    return DEFAULT_MODEL if not m or m in RETIRED else m


def write_json(path, data):
    """Write JSON so that a reader never sees half a file: a temporary file, then a
    swap. The window and background renaming are separate processes reading the
    same files. On Windows the swap fails while another process has the file open
    for a moment, so it tries again."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
    tmp.write_text(json.dumps(data), "utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def save(**kv):
    data = {**load(), **kv}
    write_json(CONFIG_DIR / "config.json", data)
    return data


# Background watching (Settings, Folders), saved under "watch". Missing or wrong values
# fall back to these. "rows" is the Folders table; "folders" (renamed) and "loops"
# (rendered into a video) are worked out from it.
WATCH_DEFAULTS = {"enabled": False, "folders": [], "profile": "propresenter", "startup_wait_min": 3,
                  "monthly_limit_usd": 5.0, "autostart": False, "rows": [], "loops": [], "service_times": []}
MAX_FOLDERS = 10
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]  # time.localtime's tm_wday


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def clean_folder(path):
    """A pasted folder path, tidied: no spaces around it, no quotes from Windows' "Copy as path"."""
    return path.strip().strip('"').strip() if isinstance(path, str) else ""


def folder_key(path):
    """One folder, one key, however it is written: G:/My Drive/x, g:\\my drive\\x\\ (as the
    window compares them too). Windows and the Mac's usual disks ignore case."""
    return clean_folder(path).replace("\\", "/").rstrip("/").lower()


def unique_folders(paths):
    """Folder paths tidied, each once, in order."""
    out, seen = [], set()
    for path in paths:
        path = clean_folder(path)
        if path and folder_key(path) not in seen:
            seen.add(folder_key(path))
            out.append(path)
    return out


def _folders(saved):
    """The watched folders: a list, each once, at most MAX_FOLDERS. A config saved
    before several folders has one "folder"."""
    raw = saved.get("folders")
    if not isinstance(raw, list):
        raw = [saved.get("folder")]
    return unique_folders(raw)[:MAX_FOLDERS]


def folder_name(path):
    """A folder's own name, the last part of its path."""
    return re.split(r"[\\/]", clean_folder(path).rstrip("\\/"))[-1] or clean_folder(path)


def row(raw):
    """One row of the Folders table, tidied, or None when it has no folder."""
    if isinstance(raw, str):
        raw = {"path": raw}
    if not isinstance(raw, dict) or not clean_folder(raw.get("path")):
        return None
    path = clean_folder(raw["path"])
    name = raw.get("name").strip() if isinstance(raw.get("name"), str) else ""
    return {"path": path, "name": name or folder_name(path),
            "rename": raw["rename"] if isinstance(raw.get("rename"), bool) else True,
            "render": raw["render"] if isinstance(raw.get("render"), bool) else False,
            "output": clean_folder(raw.get("output")),
            # the Sunday check expects something new in it every week (Service slides may not)
            "weekly": raw["weekly"] if isinstance(raw.get("weekly"), bool) else True}


def rows(raw):
    """The Folders table: tidied rows, each folder once, at most MAX_FOLDERS."""
    out, seen = [], set()
    for r in map(row, raw if isinstance(raw, list) else []):
        if r and folder_key(r["path"]) not in seen:
            seen.add(folder_key(r["path"]))
            out.append(r)
    return out[:MAX_FOLDERS]


def _minutes(hhmm):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hhmm) if isinstance(hhmm, str) else None
    return int(m.group(1)) * 60 + int(m.group(2)) if m and int(m.group(1)) < 24 and int(m.group(2)) < 60 else None


def service_times(raw):
    """[{"day": 0-6 (Monday 0), "from": "HH:MM", "to": "HH:MM"}], each starting before it
    ends on the same day; anything else is dropped."""
    out = []
    for t in raw if isinstance(raw, list) else []:
        if not isinstance(t, dict) or t.get("day") not in range(7) or isinstance(t.get("day"), bool):
            continue
        a, b = _minutes(t.get("from")), _minutes(t.get("to"))
        if a is not None and b is not None and a < b:
            out.append({"day": t["day"], "from": "%02d:%02d" % divmod(a, 60), "to": "%02d:%02d" % divmod(b, 60)})
    return out


def service_until(times, t):
    """When the service time that moment `t` falls in ends (seconds since the epoch), or None."""
    lt = time.localtime(t)
    now = lt.tm_hour * 60 + lt.tm_min
    for st in times:
        if st["day"] == lt.tm_wday and _minutes(st["from"]) <= now < _minutes(st["to"]):
            return t - now * 60 - lt.tm_sec + _minutes(st["to"]) * 60
    return None


def last_service_end(times, t):
    """When the last service time ended at or before moment `t` (seconds since the epoch),
    or None with no service times. During a service, that is the one before."""
    today, best = datetime.date.fromtimestamp(t), None
    for back in range(8):
        d = today - datetime.timedelta(days=back)
        for st in times:
            if st["day"] == d.weekday():
                h, m = divmod(_minutes(st["to"]), 60)
                end = time.mktime((d.year, d.month, d.day, h, m, 0, 0, 0, -1))
                if end <= t and (best is None or end > best):
                    best = end
    return best


def watch_settings():
    saved = load().get("watch")
    saved = saved if isinstance(saved, dict) else {}
    table = rows(saved["rows"]) if isinstance(saved.get("rows"), list) else rows(_folders(saved))
    out = dict(WATCH_DEFAULTS, rows=table, service_times=service_times(saved.get("service_times")),
               folders=[r["path"] for r in table if r["rename"]], loops=[r for r in table if r["render"]])
    for k in ("enabled", "autostart"):
        if isinstance(saved.get(k), bool):
            out[k] = saved[k]
    if isinstance(saved.get("profile"), str) and saved["profile"].strip():
        out["profile"] = saved["profile"].strip()
    if _number(saved.get("startup_wait_min")):
        out["startup_wait_min"] = min(max(int(saved["startup_wait_min"]), 0), 30)
    if _number(saved.get("monthly_limit_usd")):
        out["monthly_limit_usd"] = max(float(saved["monthly_limit_usd"]), 0.0)
    return out
