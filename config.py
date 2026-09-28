import json
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


def save(**kv):
    data = {**load(), **kv}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / "config.json"
    path.write_text(json.dumps(data), "utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return data
