import json
import os
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


# Background renaming (Settings, Watch a folder), saved under "watch". Missing or
# wrong values fall back to these.
WATCH_DEFAULTS = {"enabled": False, "folder": "", "profile": "propresenter", "startup_wait_min": 3,
                  "monthly_limit_usd": 5.0, "autostart": False}


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def watch_settings():
    saved = load().get("watch")
    saved = saved if isinstance(saved, dict) else {}
    out = dict(WATCH_DEFAULTS)
    for k in ("enabled", "autostart"):
        if isinstance(saved.get(k), bool):
            out[k] = saved[k]
    for k in ("folder", "profile"):
        if isinstance(saved.get(k), str) and saved[k].strip():
            out[k] = saved[k].strip()
    if _number(saved.get("startup_wait_min")):
        out["startup_wait_min"] = min(max(int(saved["startup_wait_min"]), 0), 30)
    if _number(saved.get("monthly_limit_usd")):
        out["monthly_limit_usd"] = max(float(saved["monthly_limit_usd"]), 0.0)
    return out
