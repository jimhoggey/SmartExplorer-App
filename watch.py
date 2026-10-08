"""Background renaming: watch one folder that Google Drive keeps in sync and rename
every new file in it with the normal naming, with nobody at the computer.

`Smart Explorer --watch` runs it; Windows starts it at sign-in when Settings says so.
The window sets it up (Settings, Watch a folder), shows what it is doing from
status.json and stops it with the stop file. Design:
docs/superpowers/specs/2026-10-08-background-renaming-design.md
"""
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import autostart
import config
import conventions
import known
import namer
import notify
import prep
import renamer
import scanner

POLL = 5  # seconds between looks at the folder
SETTLE = 10  # a file is ready once its size and modified time have held this long
FIRST_GAP, GAP = 60, 20  # quiet seconds before the first batch after start-up, and before later ones
MAX_BATCH = 200
RETRY = (300, 1800)  # a file that failed is tried again after 5 minutes, then after 30
PAID_TRIES = 2  # paid attempts per file per start-up
CHECK_AGAIN = {"connection": 300, "key": 900, "credit": 900}  # seconds before the free check runs again
FOLDER_GRACE = 120  # after the start-up wait, before saying the folder is missing
LOG_LIMIT = 1_000_000  # bytes; then the log starts again, keeping one old file

PROBLEMS = {  # each is said once, and again only after it cleared and came back
    "folder": "Smart Explorer can't find {folder}. Check Google Drive is running and signed in.",
    "nokey": "Smart Explorer has no OpenRouter key. Open Smart Explorer → Settings to add one.",
    "connection": "Smart Explorer can't reach the internet, so new files aren't renamed yet. It will try again by itself.",
    "key": "OpenRouter didn't accept the key. Open Smart Explorer → Settings to fix it.",
    "credit": "OpenRouter is out of credit. Add credit at openrouter.ai; Smart Explorer will try again by itself.",
    "limit": "Background renaming has reached this month's {limit} limit. Raise it in Settings to carry on.",
}
PAUSED = {  # the window's status bar: "Paused: …"
    "folder": "can't find {folder}",
    "nokey": "no OpenRouter key",
    "connection": "can't reach OpenRouter",
    "key": "OpenRouter didn't accept the key",
    "credit": "out of OpenRouter credit",
    "limit": "this month's {limit} limit is reached",
}


def watch_dir():
    return config.CONFIG_DIR / "watch"


def log(line):
    path = watch_dir() / "watch.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            os.replace(path, path.with_name("watch.log.1"))
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_status():
    return _read_json(watch_dir() / "status.json")


def spending():
    """What background renaming has cost, per month ("2026-10": 0.12). Only the watcher writes it."""
    return {m: v for m, v in _read_json(watch_dir() / "spend.json").items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def spent_month():
    return spending().get(time.strftime("%Y-%m"), 0.0)


def record_spend(usd):
    if usd:
        spend = spending()
        month = time.strftime("%Y-%m")
        spend[month] = round(spend.get(month, 0.0) + usd, 6)
        config.write_json(watch_dir() / "spend.json", spend)


def free_check(key):
    """Whether OpenRouter can be used now, found out without paying: None when it can,
    else "connection", "key" or "credit"."""
    r = namer.check_key(key)
    if not r["ok"]:
        return {401: "key", 403: "key", 402: "credit"}.get(r.get("status"), "connection")
    if r.get("left") is not None and r["left"] <= 0:
        return "credit"
    left = namer.credits_left(key)
    return "credit" if left is not None and left <= 0 else None


def _mock():
    return os.environ.get("SMART_EXPLORER_MOCK") == "1"


def _say(text):
    log("Said: " + text)
    why = notify.notify(text)
    if why:
        log("Notification not shown: " + why)


def _read(key, model, items, profile):
    if not key:  # test mode (SMART_EXPLORER_MOCK): no OpenRouter
        return [{"subject": Path(it["name"]).stem} for it in items], 0.0
    return namer.read_all(key, model, items, prep.encode, profile=profile)


def _name(key, model, items, descs, profile, existing):
    if not key:
        return dict(namer.mock_run(items), name_error=None)
    return namer.name_described(key, model, items, descs, profile=profile, existing=existing)


def _opens(path):
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def _list(names, show=3):
    more = len(names) - show
    return ", ".join(names[:show]) + (" and %d more" % more if more > 0 else "")


def _dollars(usd):
    return "US$" + ("%.2f" % usd).replace(".00", "")


def _clock_text(t):
    lt = time.localtime(t)
    return "%d:%02d%s" % (lt.tm_hour % 12 or 12, lt.tm_min, "am" if lt.tm_hour < 12 else "pm")


def _done_text(ready, later):
    if not ready:
        return "%s couldn't be named yet: %s" % (_plural(len(later), "file"), _list(later))
    text = "%s renamed and ready for ProPresenter" % _plural(len(ready), "file")
    if later:
        return "%s. %d couldn't be named yet: %s" % (text, len(later), _list(later))
    return "%s: %s." % (text, _list(ready))


class Watcher:
    """tick() looks at the folder once and does whatever is due. The clock, the two
    naming steps, the free check and notifications can be passed in, so tests run it
    without waiting or OpenRouter."""

    def __init__(self, clock=time.time, say=None, read=None, name=None, check=None):
        self.clock = clock
        self.say = say or _say
        self.read = read or _read
        self.name = name or _name
        self.check = check or free_check
        self.started = clock()
        self.folder = None
        self.problems = set()
        self.next_check = 0.0
        self.announced = self.checked = False
        self.batches = 0
        self.last_batch = None
        self._forget()

    def _forget(self):
        """Start afresh on the current folder's new files. A file is known by its id,
        (path, print): by print alone, duplicates in one batch would share everything."""
        self.seen = {}  # path -> {"print", "since"}: each new file and when it last changed
        self.activity = self.clock()  # when a new file last appeared or changed
        self.descs = {}  # id -> description already paid for
        self.failures = {}  # id -> {"count", "paid", "next"}
        self.given_up = set()  # ids left alone until the next start-up

    def _id(self, p):
        return (str(p), self.seen[p]["print"])

    def tick(self):
        """Look once. Returns False when watching is off, so the watcher should stop."""
        s = config.watch_settings()
        if not s["enabled"] or not s["folder"]:
            return self._status("stopped", "Background renaming is off")
        now = self.clock()
        folder = Path(s["folder"])
        if folder != self.folder:
            if self.folder is not None:
                self._forget()
            self.folder = folder
        wait = s["startup_wait_min"] * 60
        if not self.announced:
            self.announced = True
            when = "in %s" % _plural(s["startup_wait_min"], "minute") if wait else "as they arrive"
            self.say("Smart Explorer is watching %s. New files will be renamed %s." % (folder.name, when))
        if not folder.is_dir():
            if now - self.started < wait + FOLDER_GRACE:
                return self._status("waiting", "Waiting for %s to appear" % folder.name)
            self._problem("folder", s)
            return self._status("paused", "Paused: " + self._paused("folder", s))
        self._clear("folder")
        self._track(now)
        left = self.started + wait - now
        if left > 0:
            return self._status("waiting", "Waiting for Google Drive, %d min left" % math.ceil(left / 60))
        if not self.checked:
            self.checked = True
            if not self.seen:
                self.say("Checked %s: no new files." % folder.name)
        ready = self._ready(now)
        settling = [p for p in self.seen if p not in ready and self._id(p) not in self.given_up
                    and not self._later(self._id(p), now)]
        if not ready:
            if settling:
                return self._status("downloading", "Waiting for %s to finish downloading" % _plural(len(settling), "file"))
            return self._status("watching", self._watching())
        if now - self.activity < (GAP if self.batches else FIRST_GAP):
            return self._status("downloading",
                                "Waiting for %s to finish downloading" % _plural(len(ready) + len(settling), "file"))
        problem = self._blocked(s, now)
        if problem:
            return self._status("paused", "Paused: " + self._paused(problem, s))
        self._batch(s, ready[:MAX_BATCH], now)
        return self._status("watching", self._watching())

    def mark_stopped(self):
        self._status("stopped", "Background renaming stopped")

    def _status(self, state, message):
        data = {"state": state, "message": message, "folder": str(self.folder or ""), "heartbeat": time.time(),
                "last_batch": self.last_batch, "problems": sorted(self.problems)}
        try:
            config.write_json(watch_dir() / "status.json", data)
        except OSError:
            pass
        return state != "stopped"

    def _watching(self):
        text = "Watching %s" % self.folder.name
        if self.last_batch:
            text += " · last batch %s, %s" % (_clock_text(self.last_batch["at"]), _plural(self.last_batch["count"], "file"))
        return text

    def _track(self, now):
        current = dict(known.new_files(self.folder))
        for p, f in current.items():
            e = self.seen.get(p)
            if not e or e["print"] != f:
                self.seen[p] = {"print": f, "since": now}
                self.activity = now
        for p in [p for p in self.seen if p not in current]:
            del self.seen[p]

    def _later(self, fid, now):
        fail = self.failures.get(fid)
        return bool(fail and fail["next"] > now)

    def _ready(self, now):
        out = [p for p, e in self.seen.items()
               if self._id(p) not in self.given_up and now - e["since"] >= SETTLE
               and not self._later(self._id(p), now) and _opens(p)]
        return sorted(out, key=scanner.natural_key)

    def _problem(self, kind, s):
        if kind not in self.problems:
            self.problems.add(kind)
            self.say(PROBLEMS[kind].format(folder=self.folder.name, limit=_dollars(s["monthly_limit_usd"])))

    def _clear(self, kind):
        if kind in self.problems:
            self.problems.discard(kind)
            log("Cleared: " + kind)

    def _paused(self, kind, s):
        return PAUSED[kind].format(folder=self.folder.name, limit=_dollars(s["monthly_limit_usd"]))

    def _blocked(self, s, now):
        """Why no batch may be sent now (a PROBLEMS key), or None. Asks OpenRouter's free
        check before every batch, and after a problem only when it is due again."""
        key = config.load().get("key")
        for kind, bad in (("nokey", not key and not _mock()), ("limit", spent_month() >= s["monthly_limit_usd"])):
            if bad:
                self._problem(kind, s)
                return kind
            self._clear(kind)
        if not key:
            return None  # test mode: names without OpenRouter
        active = next((k for k in ("connection", "key", "credit") if k in self.problems), None)
        if active and now < self.next_check:
            return active
        found = self.check(key)
        for kind in ("connection", "key", "credit"):
            if kind != found:
                self._clear(kind)
        if found:
            self._problem(found, s)
            self.next_check = now + CHECK_AGAIN[found]
        return found

    def _batch(self, s, paths, now):
        key, model = config.load().get("key"), config.model()
        profile = conventions.resolve(s["profile"])
        ids = [self._id(p) for p in paths]
        items = [{"id": i, "path": str(p), "name": p.name, "kind": scanner.kind(p)} for i, p in enumerate(paths)]
        self.say("Renaming %s…" % _plural(len(items), "new file"))
        self._status("renaming", "Renaming %s…" % _plural(len(items), "file"))
        log("Batch: " + ", ".join(p.name for p in paths))
        failed, refused = {}, None  # failed: id -> whether a paid request failed for it
        todo = [(it, f) for it, f in zip(items, ids) if f not in self.descs]
        if todo:
            descs, cost = self.read(key, model, [it for it, _ in todo], profile)
            record_spend(cost)
            for (it, f), d in zip(todo, descs):
                if "error" not in d:
                    self.descs[f] = d
                elif d.get("status") in namer.NO_RETRY:
                    refused = d["status"]  # OpenRouter charges nothing for a request it refuses
                else:
                    failed[f] = not d.get("local")
                    log("Could not read %s: %s" % (it["name"], d["error"]))
        done = {}
        described = [(it, f) for it, f in zip(items, ids) if f in self.descs]
        if described and not refused:
            its = [it for it, _ in described]
            out = self.name(key, model, its, [self.descs[f] for _, f in described], profile, scanner.siblings(its))
            record_spend(out["cost"])
            if out["name_error"]:
                log(out["name_error"])
                failed.update((f, True) for _, f in described)  # never rename with the fallback words
            else:
                done = self._rename(items, described, out["results"], failed)
        if refused:
            kind = "credit" if refused == 402 else "key"
            self._problem(kind, s)
            self.next_check = now + CHECK_AGAIN[kind]
        names = {f: it["name"] for it, f in zip(items, ids)}
        gave_up = [names[f] for f, paid in failed.items() if self._failed(f, paid, now)]
        later = [names[f] for f in failed if f not in self.given_up]
        self.batches += 1
        if done:
            self.last_batch = {"at": now, "count": len(done)}
        if done or later:
            self.say(_done_text(list(done.values()), later))
        if gave_up:
            log("Left alone until the next start-up: " + ", ".join(gave_up))
            if len(gave_up) == 1:
                self.say("Couldn't name %s. It's still in %s under its old name." % (gave_up[0], self.folder.name))
            else:
                self.say("Couldn't name %s. They're still in %s under their old names." % (_list(gave_up), self.folder.name))

    def _rename(self, items, described, results, failed):
        """Rename the named files. Returns {id: final name} for each file now ready."""
        nums = scanner.order_numbers(items) if scanner.looks_numbered(items) else None
        planned, wanted = {}, []
        for (it, f), r in zip(described, results):
            try:
                changed = known.fingerprint(it["path"]) != f[1]
            except OSError:
                continue  # gone since it was read
            if changed:
                self.descs.pop(f, None)  # changed since it was read: it is read again as a new file
                continue
            name = "%s %s" % (nums[it["id"]], r["proposed"]) if nums else r["proposed"]
            wanted.append({"path": it["path"], "new_name": name})
            planned[it["path"]] = f
        pairs = renamer.plan(wanted)
        res = renamer.apply(pairs)
        moved = dict(pairs[:res["renamed"]])
        stuck = {old for old, _ in pairs[res["renamed"]:]}
        for old, new in moved.items():
            log("Renamed %s -> %s" % (Path(old).name, Path(new).name))
        if res.get("error"):
            log(res["error"])
        done = {}
        for path, f in planned.items():
            if path in stuck:
                failed[f] = False  # the rename failed on this computer: nothing was charged for it
                continue
            final = Path(moved.get(path, path))
            if final.is_file():
                done[f] = final.stem
        known.add(self.folder, [(Path(moved.get(p, p)).name, f[1]) for p, f in planned.items() if f in done])
        for f in done:
            self.descs.pop(f, None)
            self.failures.pop(f, None)
        return done

    def _failed(self, fid, paid, now):
        """Count a failure. Returns True when the file is now left alone until the next start-up."""
        e = self.failures.setdefault(fid, {"count": 0, "paid": 0, "next": 0.0})
        e["count"] += 1
        e["paid"] += bool(paid)
        if e["paid"] >= PAID_TRIES or e["count"] > len(RETRY):
            self.given_up.add(fid)
            self.descs.pop(fid, None)
            return True
        e["next"] = now + RETRY[e["count"] - 1]
        return False
