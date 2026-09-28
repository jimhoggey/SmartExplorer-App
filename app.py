import os
import re
import threading
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

app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"))
JOBS, LOCK = {}, threading.Lock()


def status():
    c = config.load()
    return {"has_key": bool(c.get("key")), "model": config.model(), "models": config.MODELS,
            "profiles": [{"id": k, "label": v["label"]} for k, v in conventions.PROFILES.items()],
            # the naming options last used, so the next launch starts the same way
            "profile": c.get("profile") if c.get("profile") in conventions.PROFILES else conventions.DEFAULT_PROFILE,
            "keep_order": bool(c.get("keep_order"))}


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
    config.save(**{k: v for k, v in request.get_json().items() if k in ("key", "model") and isinstance(v, str)})
    return jsonify(status())


@app.post("/api/check-key")
def api_check_key():
    return jsonify(namer.check_key(request.get_json().get("key") or config.load().get("key", "")))


@app.post("/api/scan")
def api_scan():
    paths = paths_or_none()
    if not paths:
        return jsonify(error="Not a folder or file"), 400
    items = scanner.scan(*paths)
    with ThreadPoolExecutor(8) as ex:
        thumbs = list(ex.map(thumb, items))
    return jsonify(items=[dict(i, thumb=t) for i, t in zip(items, thumbs)])


@app.post("/api/name")
def api_name():
    paths = paths_or_none()
    if not paths:
        return jsonify(error="Not a folder or file"), 400
    key = config.load().get("key")
    if not key and os.environ.get("SMART_EXPLORER_MOCK") != "1":
        return jsonify(error="Add your OpenRouter key in Settings"), 400
    body = request.get_json()
    profile = body.get("profile") if body.get("profile") in conventions.PROFILES else conventions.DEFAULT_PROFILE
    config.save(profile=profile, keep_order=bool(body.get("keep_order")))
    opts = {"profile": profile, "context": str(body.get("context") or "")[:2000],
            "keep_order": bool(body.get("keep_order"))}
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
