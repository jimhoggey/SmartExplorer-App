import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, request

import config
import conventions
import namer
import prep
import renamer
import scanner
import updater
from version import APP_VERSION

app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"))
JOBS, LOCK = {}, threading.Lock()


def spending(c):
    """What naming has cost on OpenRouter, per month ("2026-09": 0.34), as saved in the config."""
    spend = c.get("spend")
    return {m: v for m, v in spend.items() if isinstance(v, (int, float)) and not isinstance(v, bool)} \
        if isinstance(spend, dict) else {}


def record_spend(usd):
    """Add a naming batch's cost to this month's total, so Settings can show a running total."""
    if not usd:
        return
    with LOCK:
        spend = spending(config.load())
        month = time.strftime("%Y-%m")
        spend[month] = round(spend.get(month, 0.0) + usd, 6)
        config.save(spend=spend)


def status():
    c = config.load()
    spend = spending(c)
    return {"version": APP_VERSION, "has_key": bool(c.get("key")), "model": config.model(), "models": config.MODELS,
            "profiles": [{"id": k, "label": v["label"], "description": v["description"]}
                         for k, v in conventions.PROFILES.items()],
            # the naming style last used, so the next launch starts the same way
            "profile": c.get("profile") if c.get("profile") in conventions.PROFILES else conventions.DEFAULT_PROFILE,
            "spent_month": round(spend.get(time.strftime("%Y-%m"), 0.0), 6),
            "spent_total": round(sum(spend.values()), 6)}


NOT_FOUND = "Can't find that folder. Check the spelling, or use Choose folder."


def paths_or_none():
    """Absolute, existing paths from {"paths": [...]} or the older {"folder": ...}."""
    body = request.get_json(silent=True) or {}
    raw = body.get("paths") or ([body["folder"]] if body.get("folder") else [])
    ok = [str(p) for p in raw if isinstance(p, str) and p and Path(p).is_absolute() and Path(p).exists()]
    return ok or None


def thumb(item):
    try:
        return prep.thumb_b64(item["path"], item["kind"])
    except Exception:
        return ""


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/status")
def api_status():
    return jsonify(status())


@app.post("/api/settings")
def api_settings():
    with LOCK:  # a naming job can be saving its cost at the same moment
        config.save(**{k: v for k, v in request.get_json().items() if k in ("key", "model") and isinstance(v, str)})
    return jsonify(status())


PROMPT_LIMIT = 20000  # characters per field; the defaults are under 4,000


def prompts():
    """Each naming style's editable prompt parts: the defaults, what is in use now,
    and which parts have been edited."""
    out = []
    for pid, p in conventions.PROFILES.items():
        edited = conventions.edits(pid)
        out.append({"id": pid, "label": p["label"], "description": p["description"],
                    "defaults": {f: p[f] for f in conventions.FIELDS},
                    "current": {f: edited.get(f, p[f]) for f in conventions.FIELDS},
                    "edited": sorted(edited)})
    return {"profiles": out}


def prompt_draft():
    """The profile and fields posted from the prompt editor, or an error message."""
    body = request.get_json(silent=True) or {}
    if body.get("profile") not in conventions.PROFILES:
        return None, None, "Unknown naming style"
    fields = {f: body[f] for f in conventions.FIELDS if isinstance(body.get(f), str)}
    if any(len(v) > PROMPT_LIMIT for v in fields.values()):
        return None, None, "That prompt is too long (the limit is %d characters)" % PROMPT_LIMIT
    return body["profile"], fields, None


@app.get("/api/prompts")
def api_prompts():
    return jsonify(prompts())


@app.post("/api/prompts")
def api_prompts_save():
    """Save a naming style's prompt parts. Parts sent empty, or the same as the
    default, go back to the default (so later improvements to it still apply);
    parts not sent keep their saved edits."""
    profile, fields, err = prompt_draft()
    if err:
        return jsonify(error=err), 400
    with LOCK:
        saved = config.load().get("prompt_edits")
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved[profile] = conventions.merged(profile, fields)
        config.save(prompt_edits={k: v for k, v in saved.items() if v})
    return jsonify(prompts())


@app.post("/api/prompts/preview")
def api_prompts_preview():
    """The full prompts the AI would get with these parts, as sent (before the files)."""
    profile, fields, err = prompt_draft()
    if err:
        return jsonify(error=err), 400
    return jsonify(read=namer.read_prompt(profile, draft=fields), name=namer.name_prompt(profile, draft=fields))


@app.get("/api/update")
def api_update():
    """Whether a newer release is out (?force=1 asks GitHub again), and how an update in progress is going."""
    return jsonify(dict(updater.check(force=request.args.get("force") == "1"), progress=dict(updater.STATE)))


@app.post("/api/update")
def api_update_start():
    err = updater.start()
    return (jsonify(error=err), 400) if err else jsonify(progress=dict(updater.STATE))


@app.post("/api/check-key")
def api_check_key():
    return jsonify(namer.check_key(request.get_json().get("key") or config.load().get("key", "")))


@app.post("/api/scan")
def api_scan():
    paths = paths_or_none()
    if not paths:
        return jsonify(error=NOT_FOUND), 400
    items = scanner.scan(*paths)
    with ThreadPoolExecutor(8) as ex:
        thumbs = list(ex.map(thumb, items))
    return jsonify(items=[dict(i, thumb=t) for i, t in zip(items, thumbs)], numbered=scanner.looks_numbered(items))


@app.post("/api/name")
def api_name():
    paths = paths_or_none()
    if not paths:
        return jsonify(error=NOT_FOUND), 400
    key = config.load().get("key")
    if not key and os.environ.get("SMART_EXPLORER_MOCK") != "1":
        return jsonify(error="Add your OpenRouter key in Settings"), 400
    body = request.get_json()
    profile = body.get("profile") if body.get("profile") in conventions.PROFILES else conventions.DEFAULT_PROFILE
    with LOCK:
        config.save(profile=profile)
    opts = {"profile": profile, "context": str(body.get("context") or "")[:2000]}
    items = scanner.scan(*paths)
    opts["existing"] = scanner.siblings(items)
    jid = uuid.uuid4().hex
    job = JOBS[jid] = {"done": False, "total": len(items), "progress": 0, "results": {}, "cost": 0.0, "error": None}

    def on_progress(item_id, stage, proposed=None):
        with LOCK:
            job["progress"] += stage == "described"

    def work():
        try:
            if key:
                out = namer.run(key, config.model(), items, prep.encode, on_progress, **opts)
            else:
                out = namer.mock_run(items, on_progress, **opts)
            # Keyed by absolute path, never by list position: the browser's list
            # and this scan can differ if files land or leave in between.
            job["results"] = {r["path"]: {"proposed": r["proposed"], "error": r.get("error")} for r in out["results"]}
            job["cost"] = out["cost"]
            record_spend(out["cost"])
        except Exception as e:
            job["error"] = str(e)
        job["done"] = True

    threading.Thread(target=work, daemon=True).start()
    return jsonify(job=jid)


@app.get("/api/name/<job>")
def api_name_poll(job):
    return jsonify(JOBS[job]) if job in JOBS else (jsonify(error="No such job"), 404)


@app.post("/api/rename")
def api_rename():
    pairs = renamer.plan(request.get_json()["items"])
    out = renamer.apply(pairs)
    return jsonify(dict(out, moved=pairs[:out["renamed"]]))


@app.post("/api/undo")
def api_undo():
    jid = str(request.get_json().get("journal") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", jid) or not (config.CONFIG_DIR / "journal" / (jid + ".json")).is_file():
        return jsonify(error="Nothing to undo"), 404
    moved = renamer.undo(jid)
    return jsonify(restored=len(moved), moved=moved)


@app.get("/api/pick-folder")
def api_pick_folder():
    try:
        import webview
        kind = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
        picked = webview.windows[0].create_file_dialog(kind)
    except Exception:
        picked = None
    return jsonify(folder=picked[0] if picked else None)
