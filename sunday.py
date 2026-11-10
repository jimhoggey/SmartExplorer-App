"""The Sunday check on the start screen: has Smart Explorer done its job this week?

The week begins when the last service time ended (or 7 days ago, with none). For each slide
folder it says whether something new arrived since then and whether every new file is named;
for each loop, whether this week's video is made. It ticks only what it can see for itself,
says when it can't tell (the background copy not running or not checking in), and never
claims the files are the right ones: that something arrived, not what it shows.
Design: docs/superpowers/specs/2026-11-10-sunday-check-design.md
"""
import json
import os
import time
from pathlib import Path

import config
import known

WEEK = 7 * 86400
STALE = 90  # seconds without a look from the background copy before the check can't tell
KEEP = 20  # what was named lately, kept in watch/recent.json
LATEST = 4  # shown on the start screen
WORK = ("rendering", "changed", "held", "staged", "turn", "none")
BAD = ("failed", "missing")
PAUSED = {"nokey": "no OpenRouter key", "key": "OpenRouter didn't accept the key",
          "credit": "out of OpenRouter credit", "limit": "this month's AI limit is reached",
          "connection": "can't reach OpenRouter"}


def _recent_path():
    return config.CONFIG_DIR / "watch" / "recent.json"


def recent():
    """What the watcher named lately, oldest first: [{"t", "folder", "from", "to"}]."""
    try:
        data = json.loads(_recent_path().read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def note_named(folder, pairs, t):
    """The watcher renamed these (old file name, new name) in this folder at moment t."""
    pairs = list(pairs)
    if pairs:
        entries = recent() + [{"t": t, "folder": str(folder), "from": old, "to": new} for old, new in pairs]
        config.write_json(_recent_path(), entries[-KEEP:])


def week_start(times, now):
    return config.last_service_end(times, now) or now - WEEK


def _since_text(times, since):
    if not times:
        return "Over the last 7 days", "over the last 7 days"
    lt = time.localtime(since)
    day, clock = config.DAYS[lt.tm_wday], _clock(since)
    return ("Since the end of %s's service, %s %s" % (day, clock, time.strftime("%d %b", lt).lstrip("0")),
            "since %s %s" % (day, clock))


def _clock(t):
    lt = time.localtime(t)
    return "%d:%02d%s" % (lt.tm_hour % 12 or 12, lt.tm_min, "am" if lt.tm_hour < 12 else "pm")


def _when(t, now):
    same_day = time.localtime(t)[:3] == time.localtime(now)[:3]
    return _clock(t) if same_day else "%s %s" % (time.strftime("%a", time.localtime(t)), _clock(t))


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def arrived(path):
    """When a file arrived on this computer or last changed, whichever is later: its creation
    time where the system keeps one (a file Google Drive downloads is created then), and its
    modified time (an updated slide synced under the same name)."""
    st = os.stat(path)
    born = getattr(st, "st_birthtime", None)
    if born is None and os.name == "nt":
        born = st.st_ctime  # creation time on Windows
    return max(st.st_mtime, born or 0)


def _slides(r, since, since_short, problems, live, now):
    out = _slide_state(r, since, since_short, problems)
    files = out.pop("files", None)
    if files is None:
        return out
    # The second line: what it's doing now, what's in the folder, and why old files weren't named.
    parts = [live["text"]] if live and live.get("text") else []
    fresh, left = out.pop("fresh"), out.pop("left")
    where = " in " + config.folder_name(r["move_to"]) if r["move_to"] else " here"
    parts.append(_plural(files, "file") + where + (", none new " + since_short if files and not fresh else ""))
    if left:
        parts.append("%d left in the drop folder from before it was added" % left)
    added = known.recorded(r["path"])
    if added and added >= since:
        parts.append("added %s: files already in it were left as they are" % _when(added, now))
    out["detail"] = " · ".join(parts)
    return out


def _slide_state(r, since, since_short, problems):
    """A drop folder (move_to) is judged by what reached the folder ProPresenter links: that
    is where this week's files should be. What waits to be named is in the drop folder."""
    name, path = r["name"], Path(r["path"])
    shown = Path(r["move_to"]) if r["move_to"] else path
    if not path.is_dir():
        return {"name": name, "state": "bad", "text": "Can't find the folder"}
    if not shown.is_dir():
        return {"name": name, "state": "bad", "text": "Can't find %s, where named files go" % shown.name}
    try:
        dropped = known.visible(path)
        waiting = len(known.new_files(path)) if known.has_record(path) else 0
        files = known.visible(shown) if shown != path else dropped
    except OSError:
        return {"name": name, "state": "bad", "text": "Can't open the folder"}
    fresh = 0
    for p in files:
        try:
            fresh += arrived(p) >= since
        except OSError:
            pass
    # for the second line; left: a drop folder's files from before it was added, which stay put
    counts = {"files": len(files), "fresh": fresh, "left": len(dropped) - waiting if shown != path else 0}
    if waiting:
        paused = next((PAUSED[p] for p in PAUSED if p in problems), None)
        text = "%d waiting to be named" % waiting
        return dict(counts, name=name, state="bad", text="%s: %s" % (text, paused)) if paused else \
            dict(counts, name=name, state="work", text=text)
    if fresh:  # not "all named": files already there when watching began are left as they are
        return dict(counts, name=name, state="ok", text="%d new this week, nothing waiting to be named" % fresh)
    if r["weekly"]:
        return dict(counts, name=name, state="warn", text="Nothing new " + since_short)
    return dict(counts, name=name, state="ok", text="Nothing new, and it doesn't change every week")


def _loop(r, since, since_short, line, rec, now):
    name = r["name"] + ".mp4"
    state, text = (line or {}).get("state", "none"), (line or {}).get("text", "Not made yet")
    if state in BAD:
        return {"name": name, "state": "bad", "text": text}
    if state == "empty":
        return {"name": name, "state": "warn", "text": "Its folder is empty, so there's no video"}
    if state != "ok":
        return {"name": name, "state": "work", "text": text if state != "none" else "Not made yet"}
    made = (rec or {}).get("made") or 0
    if r["weekly"] and made < since:
        return {"name": name, "state": "warn", "text": "Same video as last week: nothing new " + since_short}
    return {"name": name, "state": "ok",
            "text": "Video made %s, %s" % (_when(made, now), _plural((rec or {}).get("screens", 0), "screen"))}


def _headline(rows):
    count = {s: sum(r["state"] == s for r in rows) for s in ("bad", "warn", "work")}
    if count["bad"]:
        return "bad", "A problem to fix" if count["bad"] == 1 else "%d problems to fix" % count["bad"]
    if count["warn"]:
        return "warn", "One thing to check before Sunday" if count["warn"] == 1 \
            else "%d things to check before Sunday" % count["warn"]
    if count["work"]:
        return "work", "Working on it"
    return "ok", "Ready for Sunday"


def check(settings, status, running, starting, lines, recs, now):
    """{"state": ok/warn/work/bad/unknown/off, "headline", "since", "rows": [{"name", "state",
    "text"}], "latest": [{"when", "folder", "from", "to"}]}. lines: loopwatch.lines();
    recs: loopwatch.records()."""
    if not settings["enabled"] or not settings["rows"]:
        return {"state": "off"}
    since = week_start(settings["service_times"], now)
    since_long, since_short = _since_text(settings["service_times"], since)
    problems = {p.split("|")[0] for p in (status or {}).get("problems") or []} if running else set()
    rows = []
    if "drive" in problems:
        rows.append({"name": "Google Drive", "state": "bad", "text": "Isn't running, so new files can't arrive"})
    states = {config.folder_key(k): v for k, v in ((status or {}).get("folder_states") or {}).items()
              if isinstance(v, dict)} if running else {}
    for r in settings["rows"]:
        key = config.folder_key(r["path"])
        if r["rename"]:
            rows.append(_slides(r, since, since_short, problems, states.get(key), now))
        if r["render"]:
            rows.append(_loop(r, since, since_short, lines.get(key), recs.get(key), now))
    state, headline = _headline(rows)
    quiet = now - ((status or {}).get("heartbeat") or 0)
    if not running and not starting:
        state, headline = "bad", "Smart Explorer isn't watching"
    elif running and quiet > STALE:
        state = "unknown"
        headline = "Can't tell right now: Smart Explorer hasn't checked in for %d min" % max(1, round(quiet / 60))
    names = {config.folder_key(r["path"]): r["name"] for r in settings["rows"]}
    latest = [{"when": _when(e.get("t", 0), now), "folder": names.get(config.folder_key(e.get("folder", "")),
                                                                        config.folder_name(e.get("folder", ""))),
               "from": e.get("from", ""), "to": e.get("to", "")} for e in reversed(recent()[-LATEST:])]
    return {"state": state, "headline": headline, "since": since_long, "rows": rows, "latest": latest}
