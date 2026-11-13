import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, request

import autostart
import config
import conventions
import known
import loops
import loopwatch
import namer
import prep
import renamer
import scanner
import sunday
import updater
import watch
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
    spend, background = spending(c), watch.spending()  # background renaming keeps its own record
    month = time.strftime("%Y-%m")
    return {"version": APP_VERSION, "has_key": bool(c.get("key")), "model": config.model(), "models": config.MODELS,
            "profiles": [{"id": k, "label": v["label"], "description": v["description"]}
                         for k, v in conventions.PROFILES.items()],
            # the naming style last used, so the next launch starts the same way
            "profile": c.get("profile") if c.get("profile") in conventions.PROFILES else conventions.DEFAULT_PROFILE,
            "spent_month": round(spend.get(month, 0.0) + background.get(month, 0.0), 6),
            "spent_total": round(sum(spend.values()) + sum(background.values()), 6)}


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
    w = config.watch_settings()
    if w["enabled"]:  # renamed here, so background renaming leaves them alone, in whichever watched folder
        for folder in w["folders"]:
            known.add_paths(folder, [new for _, new in out["moved"]])
    return jsonify(out)  # moved, and failed: [{path, to, why}] for files that couldn't be renamed (in use, say)


@app.post("/api/undo")
def api_undo():
    jid = str(request.get_json().get("journal") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", jid) or not (config.CONFIG_DIR / "journal" / (jid + ".json")).is_file():
        return jsonify(error="Nothing to undo"), 404
    moved = renamer.undo(jid)
    return jsonify(restored=len(moved), moved=moved)


SPAWNED = {"at": 0.0}  # when the window last started background renaming
STARTING = 15  # seconds a new background copy may take before it counts as not running


def spawn_watcher():
    watch.spawn()
    SPAWNED["at"] = time.time()


def watch_state():
    running, settings, st = watch.running(), config.watch_settings(), watch.read_status()
    now = time.time()
    until = config.service_until(settings["service_times"], now)
    starting = not running and now - SPAWNED["at"] < STARTING
    lines = loopwatch.lines(settings, st, running)
    try:
        week = sunday.check(settings, st, running, starting, lines, loopwatch.records(), now)
    except Exception as e:  # never a tick it can't back up, and never a broken Settings
        app.logger.warning("Sunday check failed: %r", e)
        week = {"state": "unknown", "headline": "Can't tell right now", "since": "", "rows": [], "latest": []}
    return {"settings": settings, "running": running, "status": st, "starting": starting,
            "spent_month": round(watch.spent_month(), 6), "can_autostart": autostart.available(),
            "autostart_on": autostart.enabled(),  # the start-up entry really exists, not just the setting
            "loops": lines,  # each Render into video row's line
            "service_until": loopwatch._clock(until) if until else None,
            "sunday": week}  # the start screen's "has it done its job this week?"


def _is_folder(f):
    return isinstance(f, str) and bool(f) and Path(f).is_absolute() and Path(f).is_dir()


@app.get("/api/watch")
def api_watch():
    return jsonify(watch_state())


def _folder_error(path, e=None):
    """Why a folder can't be watched, naming it, with the path so the window can mark its row."""
    name = Path(path).name or path
    if e is None:
        msg = "Can't find %s. Check the spelling, or use Choose." % name
    else:
        msg = "Can't open %s (%s). Check Google Drive is running, or choose another folder." % (name, e.strerror or e)
    return jsonify(error=msg, folder=path), 400


def _paths(value):
    return config.unique_folders(value) if isinstance(value, list) else []


def _rows(body):
    """The Folders table sent by the window, or the folder list of 0.7 (every folder renamed),
    or None. The count is checked before rows() keeps the first MAX_FOLDERS."""
    if isinstance(body.get("rows"), list):
        raw = body["rows"]
    elif isinstance(body.get("folders"), list):
        raw = _paths(body["folders"])
    else:
        return None
    if len({config.folder_key(r.get("path") if isinstance(r, dict) else r) for r in raw}) > config.MAX_FOLDERS:
        raise ValueError("Smart Explorer can watch up to %d folders." % config.MAX_FOLDERS)
    return config.rows(raw)


BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"%s%d" % (p, i) for p in ("COM", "LPT") for i in range(1, 10)}


def _inside(path, folder):
    a, b = config.folder_key(path), config.folder_key(folder)
    return a == b or a.startswith(b + "/")


def _writable(folder):
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".smart-explorer-", suffix=".tmp"):
            return True
    except OSError:
        return False


def _row_error(rows, enabled):
    """(message, the row's folder) for the first row Save must refuse, or None. Where the
    video goes is only checked on disk when watching is on, as the folders are."""
    videos = {}
    for r in rows:
        name, out = r["name"], r["output"]
        if not r["rename"] and not r["render"]:
            return "Tick Rename new files or Render into video for %s, or remove it." % name, r["path"]
        dest = r["move_to"] if r["rename"] else ""  # a drop folder's: where named files go
        if dest and config.folder_key(dest) == config.folder_key(r["path"]):
            return ("Choose a different folder for %s's named files, or none to name them where they are." % name,
                    r["path"])
        if dest and any(_inside(dest, o["path"]) for o in rows):
            return ("Move %s's named files to a folder Smart Explorer doesn't watch: there they'd be named again."
                    % name), r["path"]
        if dest and enabled and (not _is_folder(dest) or not _writable(dest)):
            return ("Can't move files into %s. Check the folder is there and can be written to."
                    % config.folder_name(dest)), r["path"]
        if not r["render"]:
            continue
        if not out:
            return "Choose where to save %s's video." % name, r["path"]
        if BAD_NAME.search(name) or name[-1] in ". " or name.split(".")[0].upper() in RESERVED or len(name) > 100:
            return ('A video can\'t be called "%s". Use letters, numbers, spaces and dashes.' % name), r["path"]
        if any(_inside(out, o["path"]) for o in rows):
            return ("Save %s's video outside the folders Smart Explorer watches. It would end up renamed or "
                    "inside its own loop." % name), r["path"]
        if enabled and (not _is_folder(out) or not _writable(out)):
            return ("Can't save into %s. Check the folder is there and can be written to."
                    % config.folder_name(out)), r["path"]
        same = videos.setdefault((name.lower(), config.folder_key(out)), r)
        if same is not r:
            return ("%s and %s would both save %s.mp4 in %s. Give one another name."
                    % (config.folder_name(same["path"]), config.folder_name(r["path"]), name,
                       config.folder_name(out))), r["path"]
    return None


@app.post("/api/watch/preview")
def api_watch_preview():
    """What Save would do: how many files each folder holds now (the ones renaming leaves
    as they are) and, for a loop, how many screens its video would have and whether a
    video of that name is already there."""
    try:
        rows = _rows(request.get_json(silent=True) or {}) or []
    except ValueError as e:
        return jsonify(error=str(e)), 400
    counts, videos = {}, {}
    for r in rows:
        folder = r["path"]
        if not _is_folder(folder):
            return _folder_error(folder)
        try:
            files = known.visible(folder)
        except OSError as e:
            return _folder_error(folder, e)
        counts[folder] = len(files)
        if r["render"]:
            videos[folder] = {"screens": sum(scanner.kind(p) in ("image", "video") for p in files),
                              "exists": bool(r["output"]) and loops.video_path(r["output"], r["name"]).is_file()}
    bad = _row_error(rows, True)  # Save's checks first, so the confirm never comes before an error
    if bad:
        return jsonify(error=bad[0], folder=bad[1]), 400
    return jsonify(counts=counts, loops=videos)


@app.post("/api/watch")
def api_watch_save():
    """Save the Folders settings, then start or stop background watching to match.
    Turning it on, or ticking Rename for a folder, records the files already in it,
    which are then left as they are. A row Save must refuse (a folder that can't be
    found or opened, a loop with nowhere to go) is named in the error, with its folder,
    and nothing is saved."""
    body = request.get_json(silent=True) or {}
    old = config.watch_settings()
    new = dict(old)
    for k in ("enabled", "autostart"):
        if isinstance(body.get(k), bool):
            new[k] = body[k]
    try:  # whether watching is on or off: never drop folders silently
        rows = _rows(body)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if rows is not None:
        new["rows"] = rows
    if isinstance(body.get("service_times"), list):
        new["service_times"] = config.service_times(body["service_times"])
    if body.get("profile") in conventions.PROFILES:
        new["profile"] = body["profile"]
    for k in ("startup_wait_min", "monthly_limit_usd"):
        if isinstance(body.get(k), (int, float)) and not isinstance(body.get(k), bool):
            new[k] = body[k]
    if new["enabled"] and not new["rows"]:
        return jsonify(error="Add a folder to watch first."), 400
    if new["enabled"]:
        for r in new["rows"]:
            if not _is_folder(r["path"]):
                return _folder_error(r["path"])
    bad = _row_error(new["rows"], new["enabled"])
    if bad:
        return jsonify(error=bad[0], folder=bad[1]), 400
    if new["enabled"]:
        watched = {config.folder_key(f) for f in old["folders"]} if old["enabled"] else set()
        for r in new["rows"]:
            if r["rename"] and config.folder_key(r["path"]) not in watched:  # compared as the window compares them
                try:
                    known.record_folder(r["path"])
                except OSError as e:
                    return _folder_error(r["path"], e)
    saved = {k: new[k] for k in ("enabled", "autostart", "profile", "startup_wait_min", "monthly_limit_usd",
                                 "rows", "service_times")}
    saved["folders"] = [r["path"] for r in new["rows"] if r["rename"]]  # so 0.7 still renames, if it comes back
    with LOCK:
        config.save(watch=saved)
    new = config.watch_settings()
    err = None
    if new["enabled"] and new["autostart"] and autostart.available():
        err = autostart.enable()  # also refreshes the shortcut after the app moved
        if not err and not autostart.enabled():  # read it back: never say it's there when it isn't
            err = "Smart Explorer couldn't add itself to this computer's start-up items."
    else:
        autostart.disable()
    if new["enabled"] and not watch.running():
        spawn_watcher()
    elif not new["enabled"] and watch.running():
        watch.request_stop()
    out = watch_state()
    if err:
        out["error"] = err
    return jsonify(out)


@app.post("/api/watch/start")
def api_watch_start():
    if config.watch_settings()["enabled"] and not watch.running():
        spawn_watcher()
    return jsonify(watch_state())


@app.post("/api/watch/retry")
def api_watch_retry():
    """Try again: background renaming renames the files that were in use, with the names
    they were already given (no AI), at its next look."""
    watch.request_retry()
    return jsonify(watch_state())


@app.post("/api/loops/render")
def api_loops_render():
    """Render now: the background copy renders this loop at its next look, changed or not;
    anyway: even in a service time (the window asked first)."""
    body = request.get_json(silent=True) or {}
    s = config.watch_settings()
    path = body.get("path") if isinstance(body.get("path"), str) else ""
    if not any(config.folder_key(r["path"]) == config.folder_key(path) for r in s["loops"]):
        return jsonify(error="Save this folder with Render into video ticked first."), 400
    if not s["enabled"]:
        return jsonify(error="Turn on watching these folders, and Save, to render."), 409
    loopwatch.request(path, anyway=body.get("anyway") is True)
    if not watch.running():
        spawn_watcher()
    return jsonify(watch_state())


@app.post("/api/watch/startup-items")
def api_watch_startup_items():
    autostart.show()
    return jsonify(ok=True)


@app.post("/api/watch/log")
def api_watch_log():
    path = watch.watch_dir() / "watch.log"
    if not path.exists():
        return jsonify(error="Nothing has been logged yet."), 404
    if sys.platform == "win32":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
    return jsonify(ok=True)


@app.get("/api/pick-folder")
def api_pick_folder():
    try:
        import webview
        kind = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
        picked = webview.windows[0].create_file_dialog(kind)
    except Exception:
        picked = None
    return jsonify(folder=picked[0] if picked else None)
