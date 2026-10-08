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
FOLDER_GRACE = 120  # how long the folder may be missing or unreadable (a Drive restart) before it is said
FORGET = 600  # a known file's name is forgotten once it has been gone from the folder this long
LOCK_TRIES = 8  # a quarter of a second apart: the window's running() check holds the lock for a moment
LOG_LIMIT = 1_000_000  # bytes; then the log starts again, keeping one old file

PROBLEMS = {  # each is said once, and again only after it cleared and came back
    "folder": "Smart Explorer can't find {folder}. Check Google Drive is running and signed in.",
    "listing": "Smart Explorer can't open {folder}. Check Google Drive is running and signed in.",
    "nokey": "Smart Explorer has no OpenRouter key. Open Smart Explorer → Settings to add one.",
    "connection": "Smart Explorer can't reach the internet, so new files aren't renamed yet. It will try again by itself.",
    "key": "OpenRouter didn't accept the key. Open Smart Explorer → Settings to fix it.",
    "credit": "OpenRouter is out of credit. Add credit at openrouter.ai; Smart Explorer will try again by itself.",
    "limit": "Background renaming has reached this month's {limit} limit. Raise it in Settings to carry on.",
}
PAUSED = {  # the window's status bar: "Paused: …"
    "folder": "can't find {folder}",
    "listing": "can't open {folder}",
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


def _spend(usd):
    """record_spend that cannot stop a batch: a full disk must not turn paid work into a retry."""
    try:
        record_spend(usd)
    except OSError as e:
        log("Could not record US$%.4f spent: %s" % (usd, e))


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

    def __init__(self, clock=time.time, say=None, read=None, name=None, check=None, startup=True):
        self.clock = clock
        self.startup = startup  # started with the computer: wait for Google Drive first
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
        self.unavailable_since = None  # when the folder went missing or unreadable
        self._forget()

    def _forget(self):
        """Start afresh on the current folder's new files. A file is known by its id,
        (path, print): by print alone, duplicates in one batch would share everything."""
        self.seen = {}  # path -> {"print", "since"}: each new file and when it last changed
        self.activity = self.clock()  # when a new file last appeared or changed
        self.descs = {}  # id -> description already paid for
        self.failures = {}  # id -> {"count", "paid", "next"}
        self.given_up = set()  # ids left alone until the next start-up
        self.handled = set()  # ids renamed or left alone this run, even if known.json could not record them
        self.absent = {}  # known name -> when it was first missing from the folder

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
        wait = s["startup_wait_min"] * 60 if self.startup else 0
        if not self.announced:
            self.announced = True
            when = "in %s" % _plural(s["startup_wait_min"], "minute") if wait else "as they arrive"
            self.say("Smart Explorer is watching %s. New files will be renamed %s." % (folder.name, when))
        listing, current, trouble = self._look(folder)
        if trouble:
            if self.unavailable_since is None:
                self.unavailable_since = now
            if now - self.started < wait + FOLDER_GRACE or now - self.unavailable_since < FOLDER_GRACE:
                return self._status("waiting", "Waiting for %s to appear" % folder.name)
            self._problem(trouble, s)
            return self._status("paused", "Paused: " + self._paused(trouble, s))
        self.unavailable_since = None
        self._clear("folder")
        self._clear("listing")
        self._track(now, current)
        self._forget_absent(now, listing)
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
        quiet = GAP if self.batches else FIRST_GAP
        if now - self.activity < quiet:
            if settling:
                return self._status("downloading", "Waiting for %s to finish downloading" % _plural(len(settling), "file"))
            return self._status("downloading", "Found %s. Renaming in %d s, in case more are on the way." % (
                _plural(len(ready), "new file"), math.ceil(quiet - (now - self.activity))))
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

    def _look(self, folder):
        """(the folder's files, its new files {path: print}, None), or (None, None, a
        PROBLEMS key) when it is missing or cannot be listed. A folder with no record,
        because known.json was deleted or damaged, is recorded first: its files are
        left as they are, never renamed all at once."""
        if not folder.is_dir():
            return None, None, "folder"
        try:
            if not known.has_record(folder):
                count = known.record_folder(folder)
                log("No record of %s: its %s left as they are" % (folder, _plural(count, "file")))
            return known.visible(folder), dict(known.new_files(folder)), None
        except OSError as e:
            log("Can't open %s: %s" % (folder, e))
            return None, None, "listing"

    def _remember(self, entries):
        """Know these (path, print) pairs from now on, in known.json and, should that
        fail, at least for this run."""
        entries = list(entries)
        self.handled.update((str(p), f) for p, f in entries)
        try:
            known.add(self.folder, [(Path(p).name, f) for p, f in entries])
        except OSError as e:
            log("Could not record %s: %s" % (", ".join(Path(p).name for p, _ in entries), e))

    def _track(self, now, current):
        gone = {e["print"]: p for p, e in self.seen.items() if p not in current}
        for p, f in current.items():
            if (str(p), f) in self.handled:
                continue
            e = self.seen.get(p)
            if e and e["print"] == f:
                continue
            if not e and f in gone:  # the same file under another name: someone renamed it by hand
                old = gone.pop(f)
                self._remember([(p, f)])
                log("Renamed by hand: %s -> %s, left as it is" % (old.name, p.name))
                continue
            self.seen[p] = {"print": f, "since": now}
            self.activity = now
        for p in [p for p in self.seen if p not in current]:
            del self.seen[p]

    def _forget_absent(self, now, listing):
        """Forget the names of known files gone from the folder for FORGET seconds, so a
        new file with the same name (Canva's "1.png" next week) counts as new. A file
        back within that time (Drive replacing it) keeps its name known."""
        present = {p.name.lower() for p in listing}
        names = known.names(self.folder)
        for n in [n for n in self.absent if n in present or n not in names]:
            del self.absent[n]
        for n in names - present:
            self.absent.setdefault(n, now)
        stale = {n for n, t in self.absent.items() if now - t >= FORGET}
        if stale:
            try:
                known.forget_names(self.folder, stale)
            except OSError as e:
                log("Could not forget names: %s" % e)
                return
            log("Forgot names no longer in the folder: " + ", ".join(sorted(stale)))
            for n in stale:
                del self.absent[n]

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
        failed, done = {}, {}  # failed: id -> whether a paid request failed for it; done: id -> final name
        try:
            refused = self._name_and_rename(key, model, profile, items, ids, failed, done)
        except Exception as e:  # a full disk, say: counted, so it cannot repeat (and pay) every look
            log("Batch failed: %r" % (e,))
            refused = None
            failed.update((f, True) for f in ids if f not in done and f not in failed)
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

    def _name_and_rename(self, key, model, profile, items, ids, failed, done):
        """Read what is not yet described, name the batch and rename it, filling failed
        and done. Returns OpenRouter's refusal status (402, say) or None. Descriptions are
        kept before anything else can go wrong, so paid work is never thrown away."""
        refused = None
        todo = [(it, f) for it, f in zip(items, ids) if f not in self.descs]
        if todo:
            descs, cost = self.read(key, model, [it for it, _ in todo], profile)
            for (it, f), d in zip(todo, descs):
                if "error" not in d:
                    self.descs[f] = d
                elif d.get("status") in namer.NO_RETRY:
                    refused = d["status"]  # OpenRouter charges nothing for a request it refuses
                else:
                    failed[f] = not d.get("local")
                    log("Could not read %s: %s" % (it["name"], d["error"]))
            _spend(cost)
        described = [(it, f) for it, f in zip(items, ids) if f in self.descs]
        if not described or refused:
            return refused
        its = [it for it, _ in described]
        out = self.name(key, model, its, [self.descs[f] for _, f in described], profile, scanner.siblings(its))
        _spend(out["cost"])
        if out["name_error"]:
            log(out["name_error"])
            if out.get("name_status") in namer.NO_RETRY:
                return out["name_status"]  # refused, not charged: the descriptions wait for the next try
            failed.update((f, True) for _, f in described)  # never rename with the fallback words
            return None
        done.update(self._rename(items, described, out["results"], failed))
        return None

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
        self._remember((moved.get(p, p), f[1]) for p, f in planned.items() if f in done)
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


def _lock(f):
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)


def take_lock():
    """The one-watcher lock, held until release() or the process ends (a crash leaves
    no stale lock), or None when another watcher holds it."""
    path = watch_dir() / "lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        _lock(f)
    except OSError:
        f.close()
        return None
    return f


def release(f):
    if os.name == "nt":
        import msvcrt
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    f.close()


def running():
    f = take_lock()
    if f is None:
        return True
    release(f)
    return False


def _stop_file():
    return watch_dir() / "stop"


def request_stop():
    _stop_file().parent.mkdir(parents=True, exist_ok=True)
    _stop_file().write_text("stop")


def _take_stop():
    try:
        _stop_file().unlink()
        return True
    except FileNotFoundError:
        return False


def stop_and_wait(timeout=10.0, sleep=time.sleep):
    """Ask a running watcher to stop and wait for it. Returns True once none is running."""
    if not running():
        return True
    request_stop()
    for _ in range(int(timeout / 0.25)):
        sleep(0.25)
        if not running():
            return True
    return False


def spawn(popen=subprocess.Popen):
    """Start a watcher that outlives the window."""
    _take_stop()  # a stop asked of an earlier watcher must not stop this one
    if sys.platform == "win32":
        kw = {"creationflags": getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    else:
        kw = {"start_new_session": True}
    popen(autostart.watch_command(now=True), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, close_fds=True, **kw)


def main(sleep=time.sleep, watcher=None, now=False):
    """Watch until stopped or switched off. Returns at once when another watcher runs."""
    lock = take_lock()
    for _ in range(LOCK_TRIES - 1):  # the window may be checking running() at this very moment
        if lock is not None:
            break
        sleep(0.25)
        lock = take_lock()
    if lock is None:
        return 0
    _take_stop()
    w = watcher or Watcher(startup=not now)  # now: started from the window, the computer is already up
    log("Started")
    try:
        while True:
            if _take_stop():
                if hasattr(w, "mark_stopped"):
                    w.mark_stopped()
                log("Stopped")
                break
            try:
                if not w.tick():
                    log("Watching is off: stopped")
                    break
            except Exception as e:  # one bad look must not end the watching
                log("Error: %r" % (e,))
            sleep(POLL)
    finally:
        release(lock)
    return 0
