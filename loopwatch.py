"""Loop videos in the background (Settings, Folders, Render into video). When a loop
folder's screens change, they are rendered into one video (loops.py) and swapped into
the row's save-to folder, outside service times. The Watcher in watch.py calls
Loops.tick() on every look, before renaming, so a renaming problem never holds a loop
up. Loops don't use the AI: no key, no credit and no internet don't stop them.
Design: docs/superpowers/specs/2026-11-06-loop-builder-design.md.
"""
import errno
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path

import config
import loops

QUIET = float(os.environ.get("SMART_EXPLORER_LOOP_QUIET", 30))  # seconds with no change before a render
SWAP_AGAIN = float(os.environ.get("SMART_EXPLORER_LOOP_SWAP_AGAIN", 60))  # between tries at a refused swap
SAY_IN_USE = 600  # a swap refused this long is said, once
RETRY = (300, 1800)  # a failed render is tried again after 5 minutes, then every 30 (and on the next change)
FOLDER_GRACE = 120  # how long a loop folder may be missing (a Drive restart) before it is said
MIN_TIMEOUT = 600  # a render is stopped after this, or three times the loop's length if longer
WORKING = ("rendering", "changed", "held", "staged", "turn", "empty")

SAY = {
    "updated": "{name} updated: {screens}, {length}.",
    "left_out": "{name}: couldn't use {files}, so {it} left out. The other {rest} in the video.",
    "failed": "Couldn't update {name}: {why}. The old video is still in place. Smart Explorer will try again in {when}.",
    "empty": "{name}'s folder is empty, so the old video was kept.",
    "folder": "Smart Explorer can't find the folder for {name}. Check Google Drive is running and signed in.",
    "output": "Smart Explorer can't save {name} into {output}. Check the folder is there.",
    "in_use": "ProPresenter is still using {video}. The new one goes in as soon as it stops playing.",
}


def state_path():
    return config.CONFIG_DIR / "loops.json"


def records():
    """What each loop's current video was made from, by the source folder's key."""
    try:
        data = json.loads(state_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _requests_path():
    return config.CONFIG_DIR / "watch" / "render.json"


def request(path, anyway=False):
    """Render now (the window's button): render this loop at the next look, changed or
    not; anyway: even in a service time, and swap it in then too."""
    try:
        asked = json.loads(_requests_path().read_text("utf-8"))
    except (OSError, ValueError):
        asked = []
    asked = [a for a in asked if isinstance(a, dict)] + [{"path": path, "anyway": bool(anyway)}]
    config.write_json(_requests_path(), asked)


def _take_requests():
    try:
        asked = json.loads(_requests_path().read_text("utf-8"))
        _requests_path().unlink()
    except (OSError, ValueError):
        return []
    return [a for a in asked if isinstance(a, dict) and isinstance(a.get("path"), str)]


def listing(folder):
    """[[name, size, modified ns]] for the folder's screens, in order: any added, deleted,
    renamed or edited file changes it. Raises OSError when the folder can't be listed."""
    out = []
    for p in loops.screens(folder):
        st = p.stat()
        out.append([p.name, st.st_size, st.st_mtime_ns])
    return out


def _render(paths, work):
    """Start rendering: (the ffmpeg process, the loop's length, files left out), or
    (None, 0, left out) when none of the screens could be read."""
    clips, left_out = loops.plan(paths, work)
    if not clips:
        return None, 0.0, left_out
    proc = loops.start(loops.command(clips, Path(work) / "render.mp4", work), work)
    return proc, loops.length(clips), left_out


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _clock(t):
    lt = time.localtime(t)
    return "%d:%02d%s" % (lt.tm_hour % 12 or 12, lt.tm_min, "am" if lt.tm_hour < 12 else "pm")


def length_text(secs):
    m, s = divmod(int(round(secs)), 60)
    return "%d min %02d s" % (m, s) if m else "%d s" % s


def made_text(name, rec, now=None):
    """The row's line for an up-to-date loop: Pre-service loop.mp4 · 9 screens · 2 min 05 s · made 8:14am."""
    made = rec.get("made") or 0
    when = _clock(made) if time.localtime(made)[:3] == time.localtime(now or time.time())[:3] \
        else time.strftime("%d %b", time.localtime(made)).lstrip("0")
    return "%s.mp4 · %s · %s · made %s" % (name, _plural(rec.get("screens", 0), "screen"),
                                            length_text(rec.get("length", 0)), when)


def _why(tail):
    return "the disk is full" if "No space left" in tail else "ffmpeg stopped with an error (the details are in the log)"


def _os_why(e):
    return "the disk is full" if getattr(e, "errno", None) == errno.ENOSPC else (e.strerror or str(e)).rstrip(".").lower()


class Loop:
    """One Render into video row: its screens as last seen, and its render or swap."""

    def __init__(self, row, now):
        self.files = None  # the screens at the last look
        self.changed = now  # when they last changed (or the row was added)
        self.proc = None  # ffmpeg, while rendering
        self.made_from = None  # the screens the render or staged video is made from
        self.left_out, self.total, self.started = [], 0.0, 0.0
        self.staged, self.refused_since, self.next_swap = False, None, 0.0
        self.fails, self.next_try, self.failed_files, self.error = 0, 0.0, None, None
        self.forced = False  # Render now
        self.anyway_until = 0.0  # Render now confirmed in a service time: until that one ends, or it is swapped in
        self.unavailable_since = self.output_missing_since = None
        self.state, self.text, self.bar, self.progress = "none", "Not rendered yet", "", 0.0
        self.use(row)

    def use(self, row):
        self.path, self.name, self.output, self.rename = Path(row["path"]), row["name"], row["output"], row["rename"]
        self.key = config.folder_key(row["path"])
        self.work = config.CONFIG_DIR / "loops" / hashlib.sha1(self.key.encode()).hexdigest()[:12]

    def show(self, state, text, bar="", progress=0.0):
        self.state, self.text, self.bar, self.progress = state, text, bar, progress


class Loops:
    """Every loop row, looked at once per tick. At most one renders at a time, in the
    table's order. The renderer, notifications and log can be passed in for tests."""

    def __init__(self, say, log, render=None):
        self.say, self.log, self.render = say, log, render or _render
        self.loops = {}  # folder key -> Loop, in the table's order
        self.said = set()  # "kind|key": each problem said once, and again only after it cleared
        self.unsaved = {}  # records loops.json couldn't take: without them each look would render again

    def tick(self, s, now, ready_at, renaming):
        """ready_at: when the start-up wait ends. renaming(path): whether renaming still has
        new files there. Returns (rank, text) for the status bar: 3 a problem, 2 work,
        1 all good, 0 no loops."""
        self._sync(s["loops"], now)
        until = config.service_until(s["service_times"], now)
        for a in _take_requests():
            l = self.loops.get(config.folder_key(a["path"]))
            if not l:
                continue
            if a.get("anyway") is True and until:
                l.anyway_until = until
            if not (l.proc or l.staged):  # otherwise a new video is on its way already
                l.forced = True
            self.log("Render now: %s%s" % (l.name, " (in a service time)" if l.anyway_until > now else ""))
        recs = dict(records(), **self.unsaved)
        for l in list(self.loops.values()):
            busy = next((o for o in self.loops.values() if o.proc and o is not l), None)
            try:
                self._look(l, recs, now, until, ready_at, renaming, busy)
            except Exception as e:  # one loop's trouble (a locked file, say) must not stop the others
                self.log("Loop error in %s: %r" % (l.name, e))
        return self.note()

    @staticmethod
    def _held(l, now, until):
        """In a service time, unless Render now was confirmed for this one."""
        return bool(until) and now >= l.anyway_until

    def _sync(self, rows, now):
        new = {}
        for r in rows:
            k = config.folder_key(r["path"])
            l = self.loops.get(k)
            if l and (l.name, config.folder_key(l.output)) != (r["name"], config.folder_key(r["output"])):
                self._drop(l, "its name or save-to folder changed")  # rendered again under the new name
                l = None
            if l:
                l.use(r)  # the same loop: picks up Rename ticked or not
            new[k] = l or Loop(r, now)
        for k, l in self.loops.items():
            if k not in new:
                self._drop(l, "it was removed")
        self.loops = new

    def _drop(self, l, why):
        """Stop a render and take back a staged video. The video in place stays."""
        if l.proc:
            self._stop(l, why)
        if l.staged:
            loops.clear_stage(l.output, l.name)
            l.staged = False
        for kind in SAY:
            self.said.discard("%s|%s" % (kind, l.key))

    def stop_all(self):
        for l in self.loops.values():
            if l.proc:
                self._stop(l, "watching stopped")

    def _stop(self, l, why):
        try:
            l.proc.kill()
            l.proc.wait(timeout=10)
        except Exception:
            pass
        l.proc = None
        shutil.rmtree(l.work, ignore_errors=True)
        self.log("Stopped rendering %s: %s" % (l.name, why))

    def _problem(self, kind, l, **kw):
        k = "%s|%s" % (kind, l.key)
        if k not in self.said:
            self.said.add(k)
            self.say(SAY[kind].format(name=l.name, **kw))

    def _clear(self, kind, l):
        self.said.discard("%s|%s" % (kind, l.key))

    def _look(self, l, recs, now, until, ready_at, renaming, busy):
        try:
            if not l.path.is_dir():
                raise FileNotFoundError(l.path)
            files = listing(l.path)
        except OSError:
            l.unavailable_since = l.unavailable_since or now
            if l.proc:  # else it would hold every other loop up, and run on into a service time
                self._stop(l, "its folder can't be found")
            l.forced, l.anyway_until = False, 0.0
            if now - l.unavailable_since >= FOLDER_GRACE:
                self._problem("folder", l)
            return l.show("missing", "Can't find this folder.", "can't find the folder for %s" % l.name)
        l.unavailable_since = None
        self._clear("folder", l)
        if files != l.files:
            l.files, l.changed = files, now
            if l.proc:
                self._stop(l, "its screens changed")
            if l.staged and files != l.made_from:
                loops.clear_stage(l.output, l.name)
                l.staged = False
        if l.proc:
            return self._poll(l, recs, now, until)
        if l.staged:
            return self._swap(l, recs, now, until)
        rec = recs.get(l.key) or {}
        there = loops.video_path(l.output, l.name).is_file()
        if not l.forced and there and rec.get("files") == files and rec.get("name") == l.name \
                and config.folder_key(rec.get("output")) == config.folder_key(l.output):
            return l.show("ok", made_text(l.name, rec, now))
        if not os.path.isdir(l.output):
            l.output_missing_since = l.output_missing_since or now
            if now >= ready_at and now - l.output_missing_since >= FOLDER_GRACE:  # as for the loop folder
                self._problem("output", l, output=config.folder_name(l.output))
            l.forced, l.anyway_until = False, 0.0
            return l.show("missing", "Can't find the folder to save to.",
                          "can't save %s into %s" % (l.name, config.folder_name(l.output)))
        l.output_missing_since = None
        self._clear("output", l)
        if not files:
            if there:
                self._problem("empty", l)
            l.forced, l.anyway_until = False, 0.0
            return l.show("empty", "The folder is empty, so the old video was kept." if there
                          else "Nothing to render yet: the folder is empty.", "%s's folder is empty" % l.name)
        self._clear("empty", l)
        if l.failed_files is not None and l.failed_files != files:  # changed since it failed: try again
            l.fails, l.next_try, l.failed_files = 0, 0.0, None
        if not l.forced and now < l.next_try:
            return self._show_failed(l)
        if not l.forced and now - l.changed < QUIET:
            left = math.ceil(QUIET - (now - l.changed))
            return l.show("changed", "Changed. Rendering in %d s, in case more are on the way." % left,
                          "%s changed. Rendering in %d s, in case more are on the way." % (l.name, left))
        if not l.forced and l.rename and renaming(l.path):
            return l.show("changed", "Waiting for its new files to be renamed",
                          "%s waits for its new files to be renamed" % l.name)
        if now < ready_at:
            left = math.ceil((ready_at - now) / 60)
            return l.show("changed", "Waiting for Google Drive, %d min left" % left,
                          "Waiting for Google Drive, %d min left" % left)
        if self._held(l, now, until):
            return l.show("held", "Will render after the service, at %s." % _clock(until),
                          "%s will be updated after the service, at %s" % (l.name, _clock(until)))
        if busy:
            return l.show("turn", "Renders after %s" % busy.name, "%s renders after %s" % (l.name, busy.name))
        if self._start(l, files, now):
            self._poll(l, recs, now, until)  # a short loop may be done already

    def _start(self, l, files, now):
        """Start rendering. Returns True when ffmpeg is running."""
        loops.clear_stage(l.output, l.name)
        l.forced = False
        try:
            work = loops.fresh(l.work)
            proc, total, left_out = self.render(loops.screens(l.path), work)
        except Exception as e:  # a full disk, say
            self._failed(l, now, files, _os_why(e) if isinstance(e, OSError) else str(e))
            return False
        if proc is None:
            self._failed(l, now, files, "none of its screens could be read")
            return False
        l.proc, l.total, l.left_out, l.started, l.made_from = proc, total, left_out, now, files
        self.log("Rendering %s: %s, %s" % (l.name, _plural(len(files) - len(left_out), "screen"), length_text(total)))
        for path, why in left_out:
            self.log("Left out of %s: %s (%s)" % (l.name, path.name, why))
        l.show("rendering", "Rendering… 0%", "Rendering %s… 0%%" % l.name)
        return True

    def _poll(self, l, recs, now, until):
        code = l.proc.poll()
        if code is None:
            if self._held(l, now, until):
                self._stop(l, "a service time started")
                return l.show("held", "Will render after the service, at %s." % _clock(until),
                              "%s will be updated after the service, at %s" % (l.name, _clock(until)))
            if now - l.started > max(MIN_TIMEOUT, 3 * l.total):
                self._stop(l, "it took too long")
                return self._failed(l, now, l.made_from, "the render took too long")
            p = loops.progress(l.work, l.total)
            return l.show("rendering", "Rendering… %d%%" % (p * 100), "Rendering %s… %d%%" % (l.name, p * 100), p)
        l.proc = None
        if code != 0:
            tail = loops.tail(l.work)
            self.log("ffmpeg stopped (%s) rendering %s:\n%s" % (code, l.name, tail))
            return self._failed(l, now, l.made_from, _why(tail))
        if loops.progress(l.work, l.total) < 0.9:  # ffmpeg can finish "fine" with next to nothing written
            self.log("%s came out short:\n%s" % (l.name, loops.tail(l.work)))
            return self._failed(l, now, l.made_from, "the video came out shorter than its screens")
        try:
            loops.stage(l.work / "render.mp4", l.output, l.name)
        except OSError as e:
            loops.clear_stage(l.output, l.name)
            return self._failed(l, now, l.made_from, _os_why(e))
        l.staged, l.refused_since, l.next_swap = True, None, now
        return self._swap(l, recs, now, until)

    def _swap(self, l, recs, now, until):
        video = "%s.mp4" % l.name
        if self._held(l, now, until):
            return l.show("held", "New video ready: it goes in after the service, at %s." % _clock(until),
                          "%s will be updated after the service, at %s" % (l.name, _clock(until)))
        waiting = ("staged", "New video ready: waiting for ProPresenter to let go of the old one",
                   "New %s is ready: waiting for ProPresenter to let go of the old one" % l.name)
        if now < l.next_swap:
            return l.show(*waiting)
        try:
            loops.put(l.output, l.name)
        except PermissionError:
            if l.refused_since is None:
                l.refused_since = now
                self.log("%s is in use: trying again every %d s" % (video, SWAP_AGAIN))
            l.next_swap = now + SWAP_AGAIN
            if now - l.refused_since >= SAY_IN_USE:
                self._problem("in_use", l, video=video)
            return l.show(*waiting)
        except OSError as e:
            l.staged = False
            loops.clear_stage(l.output, l.name)
            return self._failed(l, now, l.made_from, _os_why(e))
        l.staged = False
        self._clear("in_use", l)
        rec = {"files": l.made_from, "name": l.name, "output": l.output, "made": now,
               "screens": len(l.made_from) - len(l.left_out), "length": l.total,
               "left_out": [p.name for p, _ in l.left_out]}
        recs[l.key] = rec
        try:
            config.write_json(state_path(), recs)
            self.unsaved.pop(l.key, None)
        except OSError as e:
            self.unsaved[l.key] = rec
            self.log("Could not record %s: %s" % (l.name, e))
        l.fails, l.next_try, l.failed_files, l.error = 0, 0.0, None, None
        l.forced, l.anyway_until = False, 0.0
        shutil.rmtree(l.work, ignore_errors=True)
        self.log("Swapped in %s in %s" % (video, l.output))
        self.say(SAY["updated"].format(name=l.name, screens=_plural(rec["screens"], "screen"),
                                       length=length_text(l.total)))
        if l.left_out:
            names = [p.name for p, _ in l.left_out]
            self.say(SAY["left_out"].format(name=l.name, files=", ".join(names), it="it was" if len(names) == 1 else "they were",
                                            rest="%s is" % _plural(rec["screens"], "screen") if rec["screens"] == 1
                                            else "%s are" % _plural(rec["screens"], "screen")))
        l.show("ok", made_text(l.name, rec, now))

    def _failed(self, l, now, files, why):
        l.fails += 1
        wait = RETRY[min(l.fails, len(RETRY)) - 1]
        l.next_try, l.failed_files, l.error = now + wait, files, why
        l.forced, l.anyway_until = False, 0.0
        self.log("Couldn't update %s: %s" % (l.name, why))
        if l.fails == 1:  # said once; the row and the status bar keep showing it
            self.say(SAY["failed"].format(name=l.name, why=why, when=_plural(wait // 60, "minute")))
        return self._show_failed(l)

    def _show_failed(self, l):
        return l.show("failed", "Last render failed: %s. Trying again at %s." % (l.error, _clock(l.next_try)),
                      "%s: last render failed. Trying again at %s" % (l.name, _clock(l.next_try)))

    def note(self):
        """(rank, text) for the status bar: a problem first, then work, then all good."""
        ls = list(self.loops.values())
        if not ls:
            return 0, ""
        for l in ls:
            if l.state in ("failed", "missing"):
                return 3, l.bar
        for l in ls:
            if l.state in WORKING:
                return 2, l.bar
        return 1, "%s up to date" % ls[0].name if len(ls) == 1 else "loops up to date"

    def status(self):
        """Each loop's state for the window's rows."""
        return [{"path": str(l.path), "key": l.key, "state": l.state, "text": l.text, "progress": round(l.progress, 3)}
                for l in self.loops.values()]


def lines(settings, status, running):
    """{folder key: {"state", "text"}} for the Settings rows: what the background copy
    says when it runs, else what the last video was made from."""
    live = {e.get("key"): e for e in (status or {}).get("loops") or [] if isinstance(e, dict)} if running else {}
    recs, out = records(), {}
    for r in settings["loops"]:
        k = config.folder_key(r["path"])
        rec = recs.get(k)
        if k in live:
            out[k] = {"state": live[k].get("state"), "text": live[k].get("text", "")}
        elif rec and rec.get("name") == r["name"] and loops.video_path(r["output"], r["name"]).is_file():
            out[k] = {"state": "ok", "text": made_text(r["name"], rec)}
        else:
            out[k] = {"state": "none", "text": "Not rendered yet"}
    return out
