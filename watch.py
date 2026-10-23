"""Background renaming: watch folders that Google Drive keeps in sync and rename
every new file in them with the normal naming, with nobody at the computer.

`Smart Explorer --watch` runs it; Windows starts it at sign-in when Settings says so.
The window sets it up (Settings, Watch folders), shows what it is doing from
status.json and stops it with the stop file. Design:
docs/superpowers/specs/2026-10-08-background-renaming-design.md (one folder) and
docs/superpowers/specs/2026-10-23-multiple-folders-design.md (several).
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
import drive as gdrive
import known
import namer
import notify
import prep
import renamer
import scanner

POLL = 5  # seconds between looks at the folders
SETTLE = 10  # a file is ready once its size and modified time have held this long
FIRST_GAP, GAP = 60, 20  # quiet seconds before a folder's first batch after start-up, and before later ones
MAX_BATCH = 200
RETRY = (300, 1800)  # a file that failed is tried again after 5 minutes, then after 30
PAID_TRIES = 2  # paid attempts per file per start-up
CHECK_AGAIN = {"connection": 300, "key": 900, "credit": 900}  # seconds before the free check runs again
FOLDER_GRACE = 120  # how long a folder may be missing or unreadable (a Drive restart) before it is said
FORGET = 600  # a known file's name is forgotten once it has been gone from the folder this long
LOCK_TRIES = 8  # a quarter of a second apart: the window's running() check holds the lock for a moment
DRIVE_EVERY = 30  # seconds between looks at whether Google Drive is running
LOG_LIMIT = 1_000_000  # bytes; then the log starts again, keeping one old file

PROBLEMS = {  # each is said once, and again only after it cleared and came back
    "folder": "Smart Explorer can't find {folder}. Check Google Drive is running and signed in.",
    "listing": "Smart Explorer can't open {folder}. Check Google Drive is running and signed in.",
    "drive": "Google Drive isn't running on this computer, so new files can't arrive in {folder}. "
             "Open Google Drive; Smart Explorer carries on by itself.",
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


def _done_text(ready, later, where=""):
    """where: " in Youth Media" when several folders are watched, else empty."""
    if not ready:
        return "%s couldn't be named yet%s: %s" % (_plural(len(later), "file"), where, _list(later))
    text = "%s renamed and ready for ProPresenter%s" % (_plural(len(ready), "file"), where)
    if later:
        return "%s. %d couldn't be named yet: %s" % (text, len(later), _list(later))
    return "%s: %s." % (text, _list(ready))


def _names(folders):
    """How a message names folders: "Sunday Media", "Sunday Media and Youth Media", "3 folders"."""
    names = [f.name for f in folders]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return "%s and %s" % tuple(names)
    return "%d folders" % len(names)


class FolderWatch:
    """What background renaming keeps for one watched folder: its new files, their quiet
    minute, paid descriptions, retries and record. A file is known by its id,
    (path, print): by print alone, duplicates in one batch would share everything."""

    def __init__(self, path, now):
        self.path = Path(path)
        self.name = self.path.name or str(self.path)
        self.seen = {}  # path -> {"print", "since"}: each new file and when it last changed
        self.activity = now  # when a new file last appeared or changed
        self.descs = {}  # id -> description already paid for
        self.failures = {}  # id -> {"count", "paid", "next"}
        self.given_up = set()  # ids left alone until the next start-up
        self.handled = set()  # ids renamed or left alone this run, even if known.json could not record them
        self.absent = {}  # known name -> when it was first missing from the folder
        self.unavailable_since = None  # when the folder went missing or unreadable
        self.batches = 0

    def id(self, p):
        return (str(p), self.seen[p]["print"])

    def look(self):
        """(the folder's files, its new files {path: print}, None), or (None, None, a
        PROBLEMS key) when it is missing or cannot be listed. A folder with no record,
        because known.json was deleted or damaged, is recorded first: its files are
        left as they are, never renamed all at once."""
        if not self.path.is_dir():
            return None, None, "folder"
        try:
            if not known.has_record(self.path):
                count = known.record_folder(self.path)
                log("No record of %s: its %s left as they are" % (self.path, _plural(count, "file")))
            return known.visible(self.path), dict(known.new_files(self.path)), None
        except OSError as e:
            log("Can't open %s: %s" % (self.path, e))
            return None, None, "listing"

    def remember(self, entries):
        """Know these (path, print) pairs from now on, in known.json and, should that
        fail, at least for this run."""
        entries = list(entries)
        self.handled.update((str(p), f) for p, f in entries)
        try:
            known.add(self.path, [(Path(p).name, f) for p, f in entries])
        except OSError as e:
            log("Could not record %s: %s" % (", ".join(Path(p).name for p, _ in entries), e))

    def track(self, now, current):
        gone = {e["print"]: p for p, e in self.seen.items() if p not in current}
        for p, f in current.items():
            if (str(p), f) in self.handled:
                continue
            e = self.seen.get(p)
            if e and e["print"] == f:
                continue
            if not e and f in gone:  # the same file under another name: someone renamed it by hand
                old = gone.pop(f)
                self.remember([(p, f)])
                log("Renamed by hand: %s -> %s, left as it is" % (old.name, p.name))
                continue
            self.seen[p] = {"print": f, "since": now}
            self.activity = now
        for p in [p for p in self.seen if p not in current]:
            del self.seen[p]

    def forget_absent(self, now, listing):
        """Forget the names of known files gone from the folder for FORGET seconds, so a
        new file with the same name (Canva's "1.png" next week) counts as new. A file
        back within that time (Drive replacing it) keeps its name known."""
        present = {p.name.lower() for p in listing}
        names = known.names(self.path)
        for n in [n for n in self.absent if n in present or n not in names]:
            del self.absent[n]
        for n in names - present:
            self.absent.setdefault(n, now)
        stale = {n for n, t in self.absent.items() if now - t >= FORGET}
        if stale:
            try:
                known.forget_names(self.path, stale)
            except OSError as e:
                log("Could not forget names: %s" % e)
                return
            log("Forgot names no longer in %s: %s" % (self.name, ", ".join(sorted(stale))))
            for n in stale:
                del self.absent[n]

    def later(self, fid, now):
        fail = self.failures.get(fid)
        return bool(fail and fail["next"] > now)

    def ready(self, now):
        out = [p for p, e in self.seen.items()
               if self.id(p) not in self.given_up and now - e["since"] >= SETTLE
               and not self.later(self.id(p), now) and _opens(p)]
        return sorted(out, key=scanner.natural_key)

    def settling(self, ready, now):
        """New files not ready yet: still downloading (not those waiting to be tried again)."""
        return [p for p in self.seen if p not in ready and self.id(p) not in self.given_up
                and not self.later(self.id(p), now)]

    def failed(self, fid, paid, now):
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


class Watcher:
    """tick() looks at every watched folder once and does whatever is due. Each folder
    keeps its own FolderWatch; the start-up wait, the free key check, the monthly limit
    and the Google Drive check are shared. The clock, the two naming steps, the free
    check, the Drive check and notifications can be passed in, so tests run it without
    waiting or OpenRouter."""

    def __init__(self, clock=time.time, say=None, read=None, name=None, check=None, startup=True, drive=None):
        self.clock = clock
        self.startup = startup  # started with the computer: wait for Google Drive first
        self.drive = drive or gdrive.running  # True, False, or None when it can't tell
        self.drive_up, self.drive_asked, self.drive_down_since = None, float("-inf"), None
        self.say = say or _say
        self.read = read or _read
        self.name = name or _name
        self.check = check or free_check
        self.started = clock()
        self.folders = {}  # known.key(path) -> FolderWatch, in the settings' order
        self.problems = set()  # PROBLEMS keys; one about a single folder is "kind|path"
        self.next_check = 0.0
        self.announced = self.checked = False
        self.last_batch = None

    @property
    def failures(self):
        """Every folder's failures, together."""
        out = {}
        for fw in self.folders.values():
            out.update(fw.failures)
        return out

    def _where(self, fw):
        """" in Youth Media" when several folders are watched: one folder's texts stay as they were."""
        return " in %s" % fw.name if len(self.folders) > 1 else ""

    def _sync(self, now, paths):
        """Follow the settings: a new folder gets its FolderWatch, a removed one is dropped."""
        folders = {}
        for path in paths:
            k = known.key(path)
            folders[k] = self.folders.get(k) or FolderWatch(path, now)
        for k, fw in self.folders.items():
            if k not in folders:
                self._clear("folder", fw)
                self._clear("listing", fw)
                log("No longer watching %s" % fw.path)
        self.folders = folders

    def tick(self):
        """Look once. Returns False when watching is off, so the watcher should stop."""
        s = config.watch_settings()
        if not s["enabled"] or not s["folders"]:
            return self._status("stopped", "Background renaming is off")
        now = self.clock()
        self._sync(now, s["folders"])
        wait = s["startup_wait_min"] * 60 if self.startup else 0
        if not self.announced:
            self.announced = True
            when = "in %s" % _plural(s["startup_wait_min"], "minute") if wait else "as they arrive"
            self.say("Smart Explorer is watching %s. New files will be renamed %s." % (_names(self.folders.values()), when))
        looked, troubled = [], []  # folders looked at; (folder, PROBLEMS key) for those that couldn't be
        for fw in self.folders.values():
            listing, current, trouble = fw.look()
            if trouble:
                if fw.unavailable_since is None:
                    fw.unavailable_since = now
                if now - self.started >= wait + FOLDER_GRACE and now - fw.unavailable_since >= FOLDER_GRACE:
                    self._problem(trouble, s, fw)
                troubled.append((fw, trouble))
                continue
            fw.unavailable_since = None
            self._clear("folder", fw)
            self._clear("listing", fw)
            fw.track(now, current)
            fw.forget_absent(now, listing)
            looked.append(fw)
        if not looked:  # no folder to look at: say why, as for one folder
            fw, trouble = troubled[0]
            if self._key(trouble, fw) in self.problems:
                return self._status("paused", "Paused: " + self._paused(trouble, s, fw))
            return self._status("waiting", "Waiting for %s to appear" % fw.name)
        self._check_drive(s, now, wait)
        left = self.started + wait - now
        if left > 0:
            return self._status("waiting", "Waiting for Google Drive, %d min left" % math.ceil(left / 60))
        if not self.checked:
            self.checked = True
            if not any(fw.seen for fw in looked) and self.drive_up is not False:  # Drive off: "no new files" would mislead
                self.say("Checked %s: no new files." % _names(looked))
        busy = None  # what the first folder still waiting on downloads or its quiet minute shows
        for fw in looked:
            ready = fw.ready(now)
            settling = fw.settling(ready, now)
            where = self._where(fw)
            downloading = ("downloading", "Waiting for %s to finish downloading%s" % (_plural(len(settling), "file"), where))
            if not ready:
                busy = busy or (downloading if settling else None)
                continue
            quiet = GAP if fw.batches else FIRST_GAP
            if now - fw.activity < quiet:
                busy = busy or (downloading if settling else (
                    "downloading", "Found %s%s. Renaming in %d s, in case more are on the way." % (
                        _plural(len(ready), "new file"), where, math.ceil(quiet - (now - fw.activity)))))
                continue
            problem = self._blocked(s, now)
            if problem:
                return self._status("paused", "Paused: " + self._paused(problem, s))
            self._batch(s, fw, ready[:MAX_BATCH], now)
        if busy:
            return self._status(*busy)
        return self._status("watching", self._watching(troubled))

    def mark_stopped(self):
        self._status("stopped", "Background renaming stopped")

    def _check_drive(self, s, now, wait):
        """When folders are in Google Drive, look every DRIVE_EVERY seconds whether Drive
        is running, and say once if it isn't: after the start-up wait plus FOLDER_GRACE,
        and once it has been off for FOLDER_GRACE. Renaming carries on: files already here
        can be renamed, and Drive syncs the names when it is back."""
        in_drive = [fw for fw in self.folders.values() if gdrive.is_drive_folder(fw.path)]
        if not in_drive:
            self.drive_up, self.drive_down_since = None, None
            self._clear("drive")
            return
        if now - self.drive_asked >= DRIVE_EVERY:
            self.drive_asked = now
            self.drive_up = self.drive()
        if self.drive_up is not False:
            self.drive_down_since = None
            self._clear("drive")
            return
        if self.drive_down_since is None:
            self.drive_down_since = now
            log("Google Drive isn't running")
        if now - self.started >= wait + FOLDER_GRACE and now - self.drive_down_since >= FOLDER_GRACE:
            self._problem("drive", s, folder=_names(in_drive))

    def _status(self, state, message):
        if state == "watching" and any(p == "drive" or "|" in p for p in self.problems):
            state = "warning"  # watching, but a folder is missing or nothing new can arrive
        paths = [str(fw.path) for fw in self.folders.values()]
        data = {"state": state, "message": message, "folder": paths[0] if paths else "", "folders": paths,
                "heartbeat": time.time(), "last_batch": self.last_batch, "problems": sorted(self.problems)}
        try:
            config.write_json(watch_dir() / "status.json", data)
        except OSError:
            pass
        return state != "stopped"

    def _watching(self, troubled):
        fws = list(self.folders.values())
        text = "Watching %s" % (fws[0].name if len(fws) == 1 else "%d folders" % len(fws))
        missing = [self._paused(kind, None, fw) for fw, kind in troubled if self._key(kind, fw) in self.problems]
        if missing:
            return text + " · " + "; ".join(missing)
        if "drive" in self.problems:
            return text + " · Google Drive isn't running"
        if self.last_batch:
            text += " · last batch %s, %s" % (_clock_text(self.last_batch["at"]), _plural(self.last_batch["count"], "file"))
            if len(fws) > 1:
                text += " in %s" % self.last_batch["folder"]
        return text

    @staticmethod
    def _key(kind, fw=None):
        return kind if fw is None else "%s|%s" % (kind, fw.path)

    def _problem(self, kind, s, fw=None, folder=None):
        k = self._key(kind, fw)
        if k not in self.problems:
            self.problems.add(k)
            self.say(PROBLEMS[kind].format(folder=folder or (fw.name if fw else ""),
                                           limit=_dollars(s["monthly_limit_usd"])))

    def _clear(self, kind, fw=None):
        k = self._key(kind, fw)
        if k in self.problems:
            self.problems.discard(k)
            log("Cleared: " + k)

    def _paused(self, kind, s, fw=None):
        return PAUSED[kind].format(folder=fw.name if fw else "", limit=_dollars(s["monthly_limit_usd"]) if s else "")

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

    def _batch(self, s, fw, paths, now):
        """Name and rename one folder's ready files. A batch never mixes folders: names fit
        that folder's existing files, and Keep order numbers that folder's set."""
        key, model = config.load().get("key"), config.model()
        profile = conventions.resolve(s["profile"])
        ids = [fw.id(p) for p in paths]
        items = [{"id": i, "path": str(p), "name": p.name, "kind": scanner.kind(p)} for i, p in enumerate(paths)]
        where = self._where(fw)
        self.say("Renaming %s%s…" % (_plural(len(items), "new file"), where))
        self._status("renaming", "Renaming %s%s…" % (_plural(len(items), "file"), where))
        log("Batch in %s: %s" % (fw.name, ", ".join(p.name for p in paths)))
        failed, done = {}, {}  # failed: id -> whether a paid request failed for it; done: id -> final name
        try:
            refused = self._name_and_rename(fw, key, model, profile, items, ids, failed, done)
        except Exception as e:  # a full disk, say: counted, so it cannot repeat (and pay) every look
            log("Batch failed: %r" % (e,))
            refused = None
            failed.update((f, True) for f in ids if f not in done and f not in failed)
        if refused:
            kind = "credit" if refused == 402 else "key"
            self._problem(kind, s)
            self.next_check = now + CHECK_AGAIN[kind]
        names = {f: it["name"] for it, f in zip(items, ids)}
        gave_up = [names[f] for f, paid in failed.items() if fw.failed(f, paid, now)]
        later = [names[f] for f in failed if f not in fw.given_up]
        fw.batches += 1
        if done:
            self.last_batch = {"at": now, "count": len(done), "folder": fw.name}
        if done or later:
            self.say(_done_text(list(done.values()), later, where))
        if gave_up:
            log("Left alone until the next start-up: " + ", ".join(gave_up))
            if len(gave_up) == 1:
                self.say("Couldn't name %s. It's still in %s under its old name." % (gave_up[0], fw.name))
            else:
                self.say("Couldn't name %s. They're still in %s under their old names." % (_list(gave_up), fw.name))

    def _name_and_rename(self, fw, key, model, profile, items, ids, failed, done):
        """Read what is not yet described, name the batch and rename it, filling failed
        and done. Returns OpenRouter's refusal status (402, say) or None. Descriptions are
        kept before anything else can go wrong, so paid work is never thrown away."""
        refused = None
        todo = [(it, f) for it, f in zip(items, ids) if f not in fw.descs]
        if todo:
            descs, cost = self.read(key, model, [it for it, _ in todo], profile)
            for (it, f), d in zip(todo, descs):
                if "error" not in d:
                    fw.descs[f] = d
                elif d.get("status") in namer.NO_RETRY:
                    refused = d["status"]  # OpenRouter charges nothing for a request it refuses
                else:
                    failed[f] = not d.get("local")
                    log("Could not read %s: %s" % (it["name"], d["error"]))
            _spend(cost)
        described = [(it, f) for it, f in zip(items, ids) if f in fw.descs]
        if not described or refused:
            return refused
        its = [it for it, _ in described]
        out = self.name(key, model, its, [fw.descs[f] for _, f in described], profile, scanner.siblings(its))
        _spend(out["cost"])
        if out["name_error"]:
            log(out["name_error"])
            if out.get("name_status") in namer.NO_RETRY:
                return out["name_status"]  # refused, not charged: the descriptions wait for the next try
            failed.update((f, True) for _, f in described)  # never rename with the fallback words
            return None
        done.update(self._rename(fw, items, described, out["results"], failed))
        return None

    def _rename(self, fw, items, described, results, failed):
        """Rename the named files. Returns {id: final name} for each file now ready."""
        nums = scanner.order_numbers(items) if scanner.looks_numbered(items) else None
        planned, wanted = {}, []
        for (it, f), r in zip(described, results):
            try:
                changed = known.fingerprint(it["path"]) != f[1]
            except OSError:
                continue  # gone since it was read
            if changed:
                fw.descs.pop(f, None)  # changed since it was read: it is read again as a new file
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
        fw.remember((moved.get(p, p), f[1]) for p, f in planned.items() if f in done)
        for f in done:
            fw.descs.pop(f, None)
            fw.failures.pop(f, None)
        return done


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
