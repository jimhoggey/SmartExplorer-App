# Background Renaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Smart Explorer can run with no window (`--watch`), watch one Google Drive folder, and rename every new file in it with the normal naming, with nobody at the computer.

**Architecture:** A new `watch.py` loop (one `Watcher.tick()` every 5 s) finds new files through a known-files record (`known.py`), waits for Drive downloads to settle, batches arrivals, names them through the existing two-step `namer` (split so paid descriptions can be reused) and renames them through the existing `renamer`. It talks to the window only through files in `~/.smart-explorer/watch/` (status, spend, log, lock, stop). The window gets a status bar and a "Watch a folder" Settings section; Windows start-up uses a Startup-folder shortcut (`autostart.py`) and notifications use Windows toasts or `osascript` (`notify.py`).

**Tech Stack:** Python 3.9+, Flask, vanilla JS/CSS, PowerShell (built into Windows) for toasts and shortcuts, Inno Setup, pytest, PyInstaller, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-08-background-renaming-design.md`

## Global Constraints

- Python 3.9 must work (Apple's built-in Python): no `match`, no `X | Y` type unions, no 3.10+ library calls.
- No new pip dependencies. PowerShell (Windows) and `osascript` (Mac) only through `subprocess`.
- Create and change files with the Edit/Write tools only, never through shell redirects or `sed -i`.
- New files are renamed only when **both** their name and their print (size + modified time in whole seconds) are unknown.
- Quiet gap 60 s before the first batch after start-up, 20 s before later ones; settle 10 s; poll 5 s; at most 200 files per batch.
- Start-up wait setting: default 3 minutes, range 0–30. Monthly limit setting: default US$5, minimum 0.
- At most 2 paid attempts per file per start-up; retries after 5 then 30 minutes; free check (key / credit) before every paid batch; problems re-checked every 5 min (connection) or 15 min (key, credit).
- Never rename with the naming step's fallback words.
- Notification and status text: plain words, no version numbers, exactly as in the spec's Notifications table.
- Bible references and times keep full stops (`John 3.16`, `10.30am`): the naming prompts are not changed.
- Docs a volunteer reads: one page, plain words, no version numbers, no passwords, no people's names, ends with what to do when stuck.
- `~/.smart-explorer/watch/` holds `known.json`, `status.json`, `spend.json`, `watch.log`, `lock`, `stop`. The watcher never writes `config.json`.

## Review Focus

1. **A queued file disappears before it is renamed** (Drive removes it, someone deletes it): the rest of the batch is renamed, nothing crashes, the missing file is not recorded. Test in Task 6 (`test_file_deleted_mid_batch_does_not_stop_the_rest`).
2. **The watched folder goes away and comes back** (Drive signed out, then in again): the watcher pauses, notifies once, and carries on renaming when the folder returns. Test in Task 7 (`test_folder_that_comes_back_resumes`).
3. **A hand-edited or damaged config** (wrong types in `watch`, broken JSON): settings fall back to defaults, the watcher does not crash. Test in Task 1 (`test_watch_settings_defaults_and_clamps`).
4. **A new name clashes with an existing file**: the new file gets ` (2)`, nothing is overwritten. Test in Task 6 (`test_name_clash_gets_a_number_and_overwrites_nothing`).
5. **An unexpected error in one look** (a permission error reading the folder, say): it is logged and the watcher keeps going. Test in Task 8 (`test_main_survives_an_error_in_one_tick`).

---

### Task 1: Safe settings files and watch settings

**Files:**
- Modify: `config.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces: `config.write_json(path, data)` (atomic write, retries a busy target on Windows); `config.WATCH_DEFAULTS` (dict); `config.watch_settings() -> dict` with keys `enabled: bool, folder: str, profile: str, startup_wait_min: int (0-30), monthly_limit_usd: float (>=0), autostart: bool`. `config.save(**kv)` keeps its signature.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_core.py`)

```python
def test_save_writes_atomically_and_leaves_no_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    swaps = []
    real = os.replace
    monkeypatch.setattr(config.os, "replace", lambda a, b: (swaps.append((Path(a).name, Path(b).name)), real(a, b)))
    config.save(key="sk")
    assert config.load()["key"] == "sk"
    assert swaps and swaps[0][1] == "config.json" and swaps[0][0].endswith(".tmp")
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_write_json_retries_while_the_file_is_busy(tmp_path, monkeypatch):
    calls = []
    real = os.replace

    def busy_once(a, b):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("in use")  # Windows: another process is reading it
        real(a, b)

    monkeypatch.setattr(config.os, "replace", busy_once)
    monkeypatch.setattr(config.time, "sleep", lambda s: None)
    config.write_json(tmp_path / "x.json", {"a": 1})
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": 1} and len(calls) == 2


def test_watch_settings_defaults_and_clamps(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    assert config.watch_settings() == config.WATCH_DEFAULTS
    config.save(watch={"enabled": "yes", "folder": 7, "startup_wait_min": 99, "monthly_limit_usd": -3, "autostart": True})
    s = config.watch_settings()
    assert s["enabled"] is False and s["folder"] == "" and s["autostart"] is True
    assert s["startup_wait_min"] == 30 and s["monthly_limit_usd"] == 0.0
    config.save(watch={"enabled": True, "folder": "/x", "startup_wait_min": True, "monthly_limit_usd": 12.5})
    s = config.watch_settings()
    assert s["enabled"] is True and s["folder"] == "/x" and s["startup_wait_min"] == 3 and s["monthly_limit_usd"] == 12.5
    (tmp_path / "config.json").write_text("{broken")
    assert config.watch_settings() == config.WATCH_DEFAULTS
    config.save(watch="nonsense")
    assert config.watch_settings() == config.WATCH_DEFAULTS
```

Add `import json`, `import os` and `from pathlib import Path` at the top of `tests/test_core.py` if they are not there.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_core.py -q -k "atomically or busy or watch_settings"`
Expected: FAIL (`AttributeError: module 'config' has no attribute 'write_json'` / `watch_settings`).

- [ ] **Step 3: Implement** (in `config.py`)

Add `import os` and `import time` to the imports, then replace `save` and add the watch settings:

```python
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
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass (the earlier `test_config_roundtrip_and_corrupt` still passes: `save` behaves the same).

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_core.py
git commit -m "feat: settings files are written atomically; watch settings with defaults"
```

---

### Task 2: Keep order in shared Python code

**Files:**
- Modify: `scanner.py`, `app.py` (`api_scan`), `static/app.js` (`looksNumbered`, `load`)
- Test: `tests/test_core.py`, `tests/test_app.py`

**Interfaces:**
- Produces: `scanner.looks_numbered(items) -> bool` (items: dicts with `path`, `name`); `scanner.order_numbers(items) -> list[str]` (one per item, e.g. `"01"`). `/api/scan` returns `{"items": [...], "numbered": bool}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_core.py`:

```python
def _named(*names, folder="/x/Slides"):
    return [{"path": "%s/%s" % (folder, n), "name": n} for n in names]


@pytest.mark.parametrize("names", [
    ["1.png", "2.png", "10.png"],
    ["Slide1.png", "Slide2.png", "Slide3.png"],
    ["Sermon.001.png", "Sermon.002.png"],
    ["01 Welcome.png", "02 Giving.png"],
    ["1.png", "2.png", "4.png"],  # gaps allowed: deleted slides
])
def test_looks_numbered(names):
    assert scanner.looks_numbered(_named(*names))


@pytest.mark.parametrize("names", [
    ["IMG_4521.jpg", "IMG_4522.jpg"],  # a camera's numbers, not a deck
    ["Giving.png", "Sermon.png"],
    ["1.png"],  # one file has no order to keep
    ["1.png", "1 copy.png"],
    ["1-a.png", "1-b.png"],  # the same number twice
    ["1.png", "2.png", "Giving.png"],
])
def test_looks_numbered_rejects(names):
    assert not scanner.looks_numbered(_named(*names))


def test_looks_numbered_checks_each_folder():
    assert scanner.looks_numbered(_named("1.png", "2.png") + _named("Slide1.png", "Slide2.png", folder="/y"))
    assert not scanner.looks_numbered(_named("1.png", "2.png") + _named("a.png", "b.png", folder="/y"))


def test_order_numbers_per_folder_with_at_least_two_digits():
    assert scanner.order_numbers(_named("a", "b", "c")) == ["01", "02", "03"]
    assert scanner.order_numbers(_named(*map(str, range(100))))[:2] == ["001", "002"]
    assert scanner.order_numbers(_named("a", "b") + _named("c", folder="/y")) == ["01", "02", "01"]
```

Append to `tests/test_app.py`:

```python
def test_scan_says_whether_files_are_numbered(client, folder, tmp_path):
    assert client.post("/api/scan", json={"folder": str(folder)}).get_json()["numbered"] is False
    deck = tmp_path / "deck"
    deck.mkdir()
    for n in ("1.png", "2.png", "3.png"):
        Image.new("RGB", (40, 20), "blue").save(deck / n)
    assert client.post("/api/scan", json={"folder": str(deck)}).get_json()["numbered"] is True
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_core.py tests/test_app.py -q -k "numbered or order_numbers"`
Expected: FAIL (`AttributeError: ... looks_numbered`, `KeyError: 'numbered'`).

- [ ] **Step 3: Implement**

In `scanner.py` add `from collections import Counter` and:

```python
def looks_numbered(items):
    """Whether files are numbered in sequence (1.png…14.png, Slide1…, Sermon.001…, or
    names that already start 01, 02…): renamed without numbers they would sort A to Z
    in ProPresenter, so Keep order is on for them. Every folder must be numbered, with
    small, distinct numbers: a deck (gaps allowed, for deleted slides), not a camera's
    IMG_4521. ASCII digits only, as in the window it came from."""
    if len(items) < 2:
        return False
    folders = {}
    for it in items:
        folders.setdefault(str(Path(it["path"]).parent), []).append(re.sub(r"\.[^.]+$", "", it["name"]))
    for stems in folders.values():
        lead = [re.match(r"([0-9]+)[\s._-]", s) for s in stems]
        tails = [re.sub(r"[0-9]+(?=[^0-9]*$)", "#", s, count=1) for s in stems]
        if all(lead):
            nums = [int(m.group(1)) for m in lead]
        elif all(t == tails[0] and "#" in t for t in tails):
            nums = [int(re.search(r"([0-9]+)[^0-9]*$", s).group(1)) for s in stems]
        else:
            return False
        if len(set(nums)) != len(nums) or max(nums) > 2 * len(nums):
            return False
    return True


def order_numbers(items):
    """Keep order's 01, 02… for each item: per folder, in list order, at least two digits."""
    folders = [str(Path(it["path"]).parent) for it in items]
    totals, seen, out = Counter(folders), Counter(), []
    for f in folders:
        seen[f] += 1
        out.append(str(seen[f]).zfill(max(2, len(str(totals[f])))))
    return out
```

In `app.py`, `api_scan` returns the flag:

```python
    return jsonify(items=[dict(i, thumb=t) for i, t in zip(items, thumbs)], numbered=scanner.looks_numbered(items))
```

In `static/app.js`, delete the `looksNumbered` function and its comment (lines 53–69), and in `load()` use the server's answer:

```js
      const scan = await api("scan", { paths });
      if (gen !== loadGen) return;
      items = scan.items;
      if (!afterRename) {  // new files: a fresh start, with nothing carried over from the last set
        lastCost = null;
        renamedCount = 0;
        namedProfile = null;
        drafts = null;
        // Numbered in sequence (1.png…, Slide1…): Keep order starts on (scanner.looks_numbered).
        els.order.checked = autoOrder = !!scan.numbered;
        orderHint();
      }
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scanner.py app.py static/app.js tests/test_core.py tests/test_app.py
git commit -m "refactor: Keep order's numbered-files rule moves to Python, shared by the window and background renaming"
```

---

### Task 3: Split naming into a paid read step and a naming step; free checks

**Files:**
- Modify: `namer.py`
- Test: `tests/test_namer.py`

**Interfaces:**
- Produces:
  - `namer.read_all(key, model, items, encode, on_progress=None, profile=DEFAULT_PROFILE, context="") -> (descs, cost)`: one description per item in item order; a failure is `{"error": str}` plus `"local": True` when the file could not be read on this computer (nothing sent) and `"status": int` when OpenRouter answered with an HTTP error.
  - `namer.name_described(key, model, items, descs, on_progress=None, profile=DEFAULT_PROFILE, context="", existing=()) -> {"results": [{id, path, proposed, error?}], "cost": float, "name_error": str or None}`.
  - `namer.run(...)` unchanged in signature and output.
  - `namer.check_key(key)` failure dict gains `"status"` (int or None).
  - `namer.credits_left(key) -> float or None`.
  - `namer.CREDITS_URL`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_namer.py`)

```python
def test_read_all_marks_local_failures_and_http_status(monkeypatch):
    def chat(key, model, messages, **kw):
        raise namer.NamerError("OpenRouter returned HTTP 402: no credit", status=402)

    monkeypatch.setattr(namer, "chat", chat)

    def encode(item):
        if item["id"] == 0:
            raise OSError("damaged")
        return ENC

    descs, cost = namer.read_all("k", "m", ITEMS[:2], encode)
    assert descs[0]["local"] is True and "damaged" in descs[0]["error"]
    assert descs[1]["status"] == 402 and "local" not in descs[1]


def test_name_described_reuses_descriptions_without_reading(monkeypatch):
    calls = []
    good = fake_chat()

    def chat(key, model, messages, **kw):
        calls.append(isinstance(messages[1]["content"], list))
        return good(key, model, messages, **kw)

    monkeypatch.setattr(namer, "chat", chat)
    descs = [dict(DESC), {"error": "Could not read file: x", "local": True}, dict(DESC)]
    out = namer.name_described("k", "m", ITEMS, descs)
    assert calls == [False]  # one naming request, no image reading
    assert [r["proposed"] for r in out["results"]] == ["Name 0", "1", "Name 2"]
    assert "error" in out["results"][1] and out["name_error"] is None and out["cost"] == 0.01


def test_name_described_reports_a_naming_failure(monkeypatch):
    monkeypatch.setattr(namer, "chat", fake_chat(fail_naming=True))
    out = namer.name_described("k", "m", ITEMS[:1], [dict(DESC)])
    assert out["name_error"] and "429" in out["results"][0]["error"]


def test_check_key_reports_the_http_status(monkeypatch):
    monkeypatch.setattr(namer, "urlopen", raise_(HTTPError("https://x", 401, "no", {}, io.BytesIO(b"bad key"))))
    r = namer.check_key("k")
    assert r["ok"] is False and r["status"] == 401
    monkeypatch.setattr(namer, "urlopen", raise_(URLError("down")))
    assert namer.check_key("k")["status"] is None


def test_credits_left(monkeypatch):
    seen = []

    def fake(req, timeout=None):
        seen.append(req.full_url)
        return io.BytesIO(b'{"data": {"total_credits": 10, "total_usage": 9.5}}')

    monkeypatch.setattr(namer, "urlopen", fake)
    assert namer.credits_left("k") == pytest.approx(0.5) and seen == [namer.CREDITS_URL]
    monkeypatch.setattr(namer, "urlopen", raise_(HTTPError("https://x", 403, "no", {}, io.BytesIO(b"needs another key"))))
    assert namer.credits_left("k") is None
    monkeypatch.setattr(namer, "urlopen", lambda req, timeout=None: io.BytesIO(b'{"data": {}}'))
    assert namer.credits_left("k") is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_namer.py -q -k "read_all or name_described or http_status or credits_left"`
Expected: FAIL (`AttributeError: module 'namer' has no attribute 'read_all'` …).

- [ ] **Step 3: Implement** (in `namer.py`)

Add next to `KEY_URL`:

```python
CREDITS_URL = "https://openrouter.ai/api/v1/credits"
```

Add a helper above `describe` and use it in `describe`:

```python
def _failed(e):
    """A description that failed, keeping OpenRouter's HTTP status when there was one."""
    out = {"error": str(e)}
    if getattr(e, "status", None) is not None:
        out["status"] = e.status
    return out


def describe(key, model, item, encoded, profile=conventions.DEFAULT_PROFILE, context=""):
    """One file on its own. Returns (description, cost); a failure is {"error": ...}."""
    try:
        descs, cost = read_batch(key, model, [item], [encoded], profile, context)
        return descs[0], cost
    except Exception as e:
        return _failed(e), getattr(e, "cost", 0.0)
```

Replace `run` with the two steps and a `run` that joins them:

```python
def read_all(key, model, items, encode, on_progress=None, profile=conventions.DEFAULT_PROFILE, context=""):
    """The paid step: describe every item. Returns (descriptions in item order, cost).
    A failure is {"error": ...}, with "local": True when the file could not be read on
    this computer (nothing was sent, so nothing charged) and "status" when OpenRouter
    answered with an HTTP error."""
    notify = on_progress or (lambda *a: None)
    opts = (profile, context)

    def read(batch):
        descs, cost, ready, enc = {}, 0.0, [], []
        for it in batch:
            try:
                enc.append(encode(it))
                ready.append(it)
            except Exception as e:
                descs[it["id"]] = {"error": "Could not read file: %s" % e, "local": True}
        if ready:
            try:
                got, cost = read_batch(key, model, ready, enc, *opts)
                descs.update((it["id"], d) for it, d in zip(ready, got))
            except Exception as e:
                cost = getattr(e, "cost", 0.0)
                if len(ready) == 1 or getattr(e, "status", None) in NO_RETRY:
                    descs.update((it["id"], _failed(e)) for it in ready)
                else:  # one file per request instead, so one bad file cannot sink the rest
                    for it, one in zip(ready, enc):
                        descs[it["id"]], c = describe(key, model, it, one, *opts)
                        cost += c
        for it in batch:
            notify(it["id"], "described")
        return [descs[it["id"]] for it in batch], cost

    batches = [items[i:i + READ_BATCH] for i in range(0, len(items), READ_BATCH)]
    with ThreadPoolExecutor(READ_WORKERS) as ex:
        read_out = list(ex.map(read, batches))
    return [d for ds, _ in read_out for d in ds], sum(c for _, c in read_out)


def name_described(key, model, items, descs, on_progress=None, profile=conventions.DEFAULT_PROFILE, context="",
                   existing=()):
    """The naming step, for items read_all described (descs in item order). Returns
    {"results": [{id, path, proposed, error?}], "cost": USD, "name_error": None or why
    naming failed}. An item whose description failed keeps its own name. When naming
    failed, every proposed name is the file's raw words, not a chosen name."""
    notify = on_progress or (lambda *a: None)
    ok = [{**d, "i": i, "original": it["name"]} for i, (it, d) in enumerate(zip(items, descs)) if "error" not in d]
    names, name_err, cost = name_all(key, model, ok, profile, context, existing=existing) if ok else ([], None, 0.0)
    proposed = dict(zip((d["i"] for d in ok), names))
    out = []
    for i, (it, d) in enumerate(zip(items, descs)):
        name = proposed.get(i, Path(it["name"]).stem)
        r = {"id": it["id"], "path": it["path"], "proposed": name}
        if "error" in d:
            r["error"] = d["error"]
        elif name_err:
            r["error"] = name_err
        notify(it["id"], "named", name)
        out.append(r)
    return {"results": out, "cost": cost, "name_error": name_err}


def run(key, model, items, encode, on_progress=None, profile=conventions.DEFAULT_PROFILE, context="",
        existing=()):
    """Name every item. Returns {"results": [{id, path, proposed, error?}], "cost": USD}.
    existing: names already taken by other files in the same folders."""
    descs, read_cost = read_all(key, model, items, encode, on_progress, profile, context)
    out = name_described(key, model, items, descs, on_progress, profile, context, existing)
    return {"results": out["results"], "cost": read_cost + out["cost"]}
```

Change `check_key`'s failure return and add `credits_left` after it:

```python
    except NamerError as e:
        return {"ok": False, "error": str(e), "status": e.status}
```

```python
def credits_left(key):
    """US$ of credit left on the OpenRouter account, or None when OpenRouter does not
    say (it may want a different kind of key). Free: no model runs."""
    try:
        data = _request(CREDITS_URL, key, tries=1).get("data") or {}
        return float(data["total_credits"]) - float(data["total_usage"])
    except Exception:
        return None
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass, including the existing `test_run*` tests (unchanged behaviour).

- [ ] **Step 5: Commit**

```bash
git add namer.py tests/test_namer.py
git commit -m "refactor: naming splits into a paid read step and a naming step; key checks report the HTTP status; free credit check"
```

---

### Task 4: The known-files record

**Files:**
- Create: `known.py`
- Test: `tests/test_known.py`

**Interfaces:**
- Consumes: `config.write_json`, `config.CONFIG_DIR`, `scanner.kind`, `scanner.natural_key`.
- Produces: `known.fingerprint(path) -> str` (`"size:mtime"`); `known.visible(folder) -> list[Path]`; `known.record_folder(folder) -> int`; `known.add(folder, entries)` (entries: iterable of `(name, print)`); `known.add_paths(folder, paths)`; `known.new_files(folder) -> list[(Path, print)]` in natural order; `known.same_folder(a, b) -> bool`.

- [ ] **Step 1: Write the failing tests** (`tests/test_known.py`)

```python
import os

from PIL import Image

import known


def png(path, color="red"):
    Image.new("RGB", (64, 36), color).save(path)


def names(pairs):
    return [p.name for p, _ in pairs]


def test_recorded_files_are_not_new_but_later_ones_are(tmp_path):
    png(tmp_path / "old.png")
    assert known.record_folder(tmp_path) == 1
    assert known.new_files(tmp_path) == []
    png(tmp_path / "10.png")
    png(tmp_path / "2.png", "blue")
    assert names(known.new_files(tmp_path)) == ["2.png", "10.png"]


def test_hand_renamed_and_replaced_files_are_not_new(tmp_path):
    png(tmp_path / "a.png")
    png(tmp_path / "b.png")
    known.record_folder(tmp_path)
    os.rename(tmp_path / "a.png", tmp_path / "Renamed by hand.png")  # same print
    png(tmp_path / "b.png", "green")  # an updated slide under the same name
    os.utime(tmp_path / "b.png", (1, 1))
    assert known.new_files(tmp_path) == []


def test_only_files_it_would_name_count(tmp_path):
    for n in (".hidden.png", "~$lock.png", "notes.txt", "download.tmp"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    png(tmp_path / "sub" / "deep.png")
    assert known.visible(tmp_path) == [] and known.new_files(tmp_path) == []
    assert known.record_folder(tmp_path) == 0


def test_add_and_add_paths(tmp_path):
    known.record_folder(tmp_path)
    png(tmp_path / "a.png")
    png(tmp_path / "b.png", "blue")
    known.add(tmp_path, [("A.PNG", "0:0")])  # names match whatever the case
    assert names(known.new_files(tmp_path)) == ["b.png"]
    other = tmp_path / "other"
    other.mkdir()
    png(other / "c.png")
    known.add_paths(tmp_path, [tmp_path / "b.png", other / "c.png", tmp_path / "gone.png"])
    assert known.new_files(tmp_path) == []


def test_folders_are_kept_apart_and_a_missing_folder_is_empty(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    png(a / "x.png")
    png(b / "x.png")
    known.record_folder(a)
    assert known.new_files(a) == [] and names(known.new_files(b)) == ["x.png"]
    assert known.new_files(tmp_path / "missing") == []


def test_same_folder(tmp_path):
    assert known.same_folder(tmp_path, str(tmp_path) + os.sep)
    assert known.same_folder(tmp_path / "x" / "..", tmp_path)
    assert not known.same_folder(tmp_path, tmp_path / "x")
    assert not known.same_folder("", tmp_path)


def test_damaged_record_starts_afresh(tmp_path):
    png(tmp_path / "a.png")
    path = known._path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken")
    assert names(known.new_files(tmp_path)) == ["a.png"]
    known.record_folder(tmp_path)
    assert known.new_files(tmp_path) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_known.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'known'`).

- [ ] **Step 3: Implement** (`known.py`)

```python
"""The files Smart Explorer already knows in a watched folder, so background
renaming only ever touches new ones.

For every known file it keeps the name (lower case) and a print: size and modified
time in whole seconds. A file is new only when both are unknown: a file someone
renamed by hand keeps its print, and an updated slide uploaded under the same name
keeps its name, so neither is renamed again. Kept in ~/.smart-explorer/watch/known.json,
one entry per folder.
"""
import json
import os
from pathlib import Path

import config
import scanner


def _path():
    return config.CONFIG_DIR / "watch" / "known.json"


def _key(folder):
    return os.path.normcase(os.path.abspath(str(folder)))


def same_folder(a, b):
    return bool(str(a or "")) and bool(str(b or "")) and _key(a) == _key(b)


def fingerprint(path):
    st = os.stat(path)
    return "%d:%d" % (st.st_size, int(st.st_mtime))


def _load():
    try:
        data = json.loads(_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _entry(data, folder):
    e = data.get(_key(folder))
    e = e if isinstance(e, dict) else {}
    return ({n for n in e.get("names", []) if isinstance(n, str)},
            {f for f in e.get("prints", []) if isinstance(f, str)})


def _save(data, folder, names, prints):
    data[_key(folder)] = {"names": sorted(names), "prints": sorted(prints)}
    config.write_json(_path(), data)


def visible(folder):
    """The files background renaming would name: the folder's top level only, no
    hidden files, no Office or Google Drive temporary files, only types it reads."""
    try:
        files = [p for p in Path(folder).iterdir() if p.is_file()]
    except OSError:
        return []
    return sorted((p for p in files if scanner.kind(p) and not p.name.startswith((".", "~$"))), key=scanner.natural_key)


def _prints(paths):
    out = []
    for p in paths:
        try:
            out.append((p.name, fingerprint(p)))
        except OSError:  # gone since the folder was listed
            pass
    return out


def record_folder(folder):
    """Know every file in the folder now, so watching leaves them as they are.
    Returns how many there are."""
    files = visible(folder)
    entries = _prints(files)
    _save(_load(), folder, {n.lower() for n, _ in entries}, {f for _, f in entries})
    return len(files)


def add(folder, entries):
    """Know these (name, print) pairs too."""
    entries = list(entries)
    if not entries:
        return
    data = _load()
    names, prints = _entry(data, folder)
    _save(data, folder, names | {n.lower() for n, _ in entries}, prints | {f for _, f in entries})


def add_paths(folder, paths):
    """Know these files, the ones that are in the folder (renamed in the window, say)."""
    add(folder, _prints([Path(p) for p in paths if same_folder(Path(p).parent, folder)]))


def new_files(folder):
    """The folder's new files as [(path, print)], in natural order."""
    names, prints = _entry(_load(), folder)
    return [(p, f) for p in visible(folder) for n, f in _prints([p]) if n.lower() not in names and f not in prints]
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add known.py tests/test_known.py
git commit -m "feat: known-files record for background renaming"
```

---

### Task 5: Notifications and Windows start-up

**Files:**
- Create: `notify.py`, `autostart.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Produces: `notify.notify(text, title="Smart Explorer", run=subprocess.run) -> None or str` (None when shown, else why not; never raises); `notify.command(title, text, system=None, frozen=None) -> (argv, env) or None`; `notify.APP_ID = "jimhoggey.SmartExplorer"`. `autostart.NAME = "Smart Explorer (background).lnk"`; `autostart.available(system=None) -> bool`; `autostart.shortcut() -> Path`; `autostart.watch_command() -> list[str]`; `autostart.enabled() -> bool`; `autostart.enable(run=subprocess.run) -> None or str`; `autostart.disable()`.

- [ ] **Step 1: Write the failing tests** (`tests/test_notify.py`)

```python
import base64
import subprocess
import sys
from pathlib import Path

import autostart
import notify


def test_windows_toast_escapes_text_and_picks_the_app_id():
    argv, env = notify.command("Smart Explorer", "Giving & <Offering>", system="win32", frozen=True)
    assert argv[0] == "powershell" and "-EncodedCommand" in argv
    script = base64.b64decode(argv[argv.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert "ToastNotificationManager" in script and "$env:SE_TOAST" in script
    assert "Giving &amp; &lt;Offering&gt;" in env["SE_TOAST"] and env["SE_APP_ID"] == notify.APP_ID
    assert notify.command("t", "x", system="win32", frozen=False)[1]["SE_APP_ID"] == notify.POWERSHELL_ID


def test_mac_notification_passes_text_as_arguments():
    argv, env = notify.command("Smart Explorer", 'Say "hi"', system="darwin")
    assert argv[0] == "osascript" and argv[-2:] == ["Smart Explorer", 'Say "hi"'] and env == {}
    assert notify.command("t", "x", system="linux") is None


def test_notify_never_raises(monkeypatch):
    monkeypatch.setattr(notify.sys, "platform", "darwin")
    ok = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"", b"")
    assert notify.notify("hi", run=ok) is None
    bad = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, b"", b"not allowed")
    assert notify.notify("hi", run=bad) == "not allowed"

    def boom(argv, **kw):
        raise OSError("no osascript")

    assert "no osascript" in notify.notify("hi", run=boom)
    monkeypatch.setattr(notify.sys, "platform", "linux")
    assert notify.notify("hi", run=ok)


def test_watch_command_from_source_and_installed(monkeypatch):
    argv = autostart.watch_command()
    assert argv[-2:] == [str(Path(autostart.__file__).resolve().parent / "desktop.py"), "--watch"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Apps/Smart Explorer.exe")
    assert autostart.watch_command() == ["/Apps/Smart Explorer.exe", "--watch"]


def test_autostart_only_on_windows(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "darwin")
    assert not autostart.available() and not autostart.enabled()
    assert "only" in autostart.enable(run=lambda *a, **k: None)
    autostart.disable()  # nothing to do, no error


def test_autostart_creates_and_removes_the_shortcut(monkeypatch, tmp_path):
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    seen = {}

    def run(argv, env=None, **kw):
        seen.update(env)
        Path(env["SE_LNK"]).write_bytes(b"lnk")  # what PowerShell would do
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    assert autostart.enable(run=run) is None
    assert seen["SE_LNK"].endswith(autostart.NAME) and "Startup" in seen["SE_LNK"]
    assert seen["SE_ARGS"].endswith("--watch") and autostart.enabled()
    autostart.disable()
    assert not autostart.enabled()
    fail = lambda argv, **kw: subprocess.CompletedProcess(argv, 1, b"", b"denied")
    assert "denied" in autostart.enable(run=fail)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_notify.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'notify'`).

- [ ] **Step 3: Implement**

`notify.py`:

```python
"""Desktop notifications for background renaming: a Windows toast, or a Mac
notification. Showing one must never stop the renaming, so notify() never raises."""
import base64
import os
import subprocess
import sys
from xml.sax.saxutils import escape

TITLE = "Smart Explorer"
APP_ID = "jimhoggey.SmartExplorer"  # the installer puts this on the Start menu shortcut
# Run from source there is no such shortcut; Windows then shows the toast as PowerShell's.
POWERSHELL_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
TOAST = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:SE_TOAST)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:SE_APP_ID).Show($toast)
"""
MAC = ["osascript", "-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
       "-e", "end run"]


def powershell(script):
    """argv that runs a PowerShell script without quoting trouble."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode()]


def command(title, text, system=None, frozen=None):
    """(argv, extra environment) that shows the notification, or None where there is no way."""
    system = system or sys.platform
    if system == "win32":
        installed = getattr(sys, "frozen", False) if frozen is None else frozen
        xml = ('<toast><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text>'
               "</binding></visual></toast>") % (escape(title), escape(text))
        return powershell(TOAST), {"SE_TOAST": xml, "SE_APP_ID": APP_ID if installed else POWERSHELL_ID}
    if system == "darwin":
        return MAC + [title, text], {}
    return None


def notify(text, title=TITLE, run=subprocess.run):
    """Show a notification. Returns None when it was shown, else why not (for the log)."""
    cmd = command(title, text)
    if not cmd:
        return "notifications are not available on this computer"
    argv, env = cmd
    kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}
    try:
        r = run(argv, env=dict(os.environ, **env), capture_output=True, timeout=30, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    if r.returncode == 0:
        return None
    return (r.stderr or b"").decode(errors="replace").strip()[:300] or "exit code %d" % r.returncode
```

`autostart.py`:

```python
"""Start background renaming when Windows starts: a shortcut in the user's Startup
folder, which Windows runs at sign-in. No administrator rights needed. On other
systems these do nothing."""
import os
import subprocess
import sys
from pathlib import Path

import notify

NAME = "Smart Explorer (background).lnk"  # packaging/windows-installer.iss removes this name on uninstall
SCRIPT = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SE_LNK); "
          "$s.TargetPath = $env:SE_TARGET; $s.Arguments = $env:SE_ARGS; "
          "$s.WorkingDirectory = $env:SE_DIR; $s.Save()")


def available(system=None):
    return (system or sys.platform) == "win32"


def shortcut():
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / NAME


def watch_command():
    """argv that starts background renaming: the installed app, or from source the
    same Python (pythonw on Windows, so no console window opens)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--watch"]
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return [str(windowless if windowless.exists() else exe), str(Path(__file__).resolve().parent / "desktop.py"), "--watch"]


def enabled():
    return available() and shortcut().exists()


def enable(run=subprocess.run):
    """Create (or refresh) the Startup shortcut. Returns None, or why it failed."""
    if not available():
        return "Starting with the computer is only available on Windows."
    argv = watch_command()
    shortcut().parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SE_LNK=str(shortcut()), SE_TARGET=argv[0], SE_ARGS=subprocess.list2cmdline(argv[1:]),
               SE_DIR=str(Path(argv[0]).parent))
    why = "Could not add Smart Explorer to Windows start-up: %s"
    try:
        r = run(notify.powershell(SCRIPT), env=env, capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        return why % e
    if r.returncode != 0:
        return why % ((r.stderr or b"").decode(errors="replace").strip()[:300] or "exit code %d" % r.returncode)
    return None


def disable():
    if available():
        try:
            shortcut().unlink()
        except FileNotFoundError:
            pass
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add notify.py autostart.py tests/test_notify.py
git commit -m "feat: desktop notifications and a Windows start-up shortcut for background renaming"
```

---

### Task 6: The watcher: new files, batches and renaming

**Files:**
- Create: `watch.py`
- Test: `tests/test_watch.py`

**Interfaces:**
- Consumes: Tasks 1–5 (`config.watch_settings`, `config.write_json`, `scanner.looks_numbered`, `scanner.order_numbers`, `scanner.siblings`, `namer.read_all`, `namer.name_described`, `namer.mock_run`, `namer.NO_RETRY`, `known.*`, `notify.notify`), `renamer.plan`, `renamer.apply`, `conventions.resolve`.
- Produces: `watch.Watcher(clock=time.time, say=None, read=None, name=None, check=None)` with `tick() -> bool` (False when watching is off); `read(key, model, items, profile) -> (descs, cost)`; `name(key, model, items, descs, profile, existing) -> {"results", "cost", "name_error"}`; `check(key) -> None or "connection"/"key"/"credit"`; `say(text)`. Module functions `watch_dir()`, `log(line)`, `read_status() -> dict`, `spending() -> dict`, `spent_month() -> float`, `record_spend(usd)`, `free_check(key)`. Constants `POLL, SETTLE, FIRST_GAP, GAP, MAX_BATCH, RETRY, PAID_TRIES, CHECK_AGAIN, FOLDER_GRACE, LOG_LIMIT, PROBLEMS, PAUSED`.

- [ ] **Step 1: Write the failing tests** (`tests/test_watch.py`)

```python
import json
import os
import time
from pathlib import Path

import pytest
from PIL import Image

import config
import known
import watch


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def png(path, color="red"):
    Image.new("RGB", (64, 36), color).save(path)


class Fake:
    """Stands in for OpenRouter and notifications: every file is named "Name <stem>"."""

    def __init__(self, fail_read=(), local=(), fail_name=0, refuse=None, check=None, during_read=None):
        self.reads, self.names, self.said, self.checks = [], [], [], 0
        self.fail_read, self.local, self.fail_name = set(fail_read), set(local), fail_name
        self.refuse, self.check_result, self.during_read = refuse, check, during_read

    def read(self, key, model, items, profile):
        self.reads.append([it["name"] for it in items])
        if self.during_read:
            self.during_read()
        out = []
        for it in items:
            if self.refuse:
                out.append({"error": "HTTP %d" % self.refuse, "status": self.refuse})
            elif it["name"] in self.local:
                out.append({"error": "Could not read file: damaged", "local": True})
            elif it["name"] in self.fail_read:
                out.append({"error": "Model described 0 of 1 files"})
            else:
                out.append({"subject": Path(it["name"]).stem})
        return out, 0.01 * len(items)

    def name(self, key, model, items, descs, profile, existing):
        self.names.append([it["name"] for it in items])
        if self.fail_name:
            self.fail_name -= 1
            return {"results": [{"id": it["id"], "path": it["path"], "proposed": "raw words", "error": "AI naming failed"}
                                for it in items], "cost": 0.01, "name_error": "AI naming failed (HTTP 500)"}
        return {"results": [{"id": it["id"], "path": it["path"], "proposed": "Name " + d["subject"]}
                            for it, d in zip(items, descs)], "cost": 0.02, "name_error": None}

    def check(self, key):
        self.checks += 1
        return self.check_result

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "Sunday Media"
    d.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 3})
    known.record_folder(d)
    return d


def start(fake, clock=None):
    clock = clock or Clock()
    return watch.Watcher(clock=clock, say=fake.say, read=fake.read, name=fake.name, check=fake.check), clock


def run(w, clock, seconds):
    for _ in range(int(seconds // watch.POLL)):
        w.tick()
        clock.t += watch.POLL


def files(folder):
    return sorted(p.name for p in folder.iterdir())


def test_existing_files_are_left_alone(folder):
    png(folder / "old.png")
    known.record_folder(folder)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert fake.reads == [] and files(folder) == ["old.png"]
    assert fake.said == ["Smart Explorer is watching Sunday Media. New files will be renamed in 3 minutes.",
                         "Checked Sunday Media: no new files."]


def test_new_file_is_renamed_after_the_wait_and_said(folder):
    png(folder / "welcome.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 170)
    assert fake.reads == []  # still in the start-up wait
    assert watch.read_status()["message"] == "Waiting for Google Drive, 1 min left"
    run(w, clock, 60)
    assert files(folder) == ["Name welcome.png"]
    assert fake.said[1:] == ["Renaming 1 new file…", "1 file renamed and ready for ProPresenter: Name welcome."]
    run(w, clock, 600)
    assert len(fake.reads) == 1  # its new name is known: never renamed twice
    status = watch.read_status()
    assert status["state"] == "watching" and status["message"].startswith("Watching Sunday Media · last batch ")
    assert status["message"].endswith(", 1 file") and status["last_batch"]["count"] == 1
    assert watch.spent_month() == pytest.approx(0.03)
    log = (watch.watch_dir() / "watch.log").read_text("utf-8")
    assert "Renamed welcome.png -> Name welcome.png" in log


def test_files_arriving_during_the_wait_are_one_batch(folder):
    fake = Fake()
    w, clock = start(fake)
    for n in ("giving.png", "welcome.png", "sermon.png"):
        png(folder / n)
        run(w, clock, 50)
    run(w, clock, 200)
    assert fake.reads == [["giving.png", "sermon.png", "welcome.png"]]
    assert fake.said[1] == "Renaming 3 new files…"
    assert fake.said[2] == "3 files renamed and ready for ProPresenter: Name giving, Name sermon, Name welcome."


def test_first_batch_waits_for_a_quiet_minute_later_ones_for_20_seconds(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=0))
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 10)
    png(folder / "a.png")
    run(w, clock, 50)
    assert fake.reads == []  # quiet for under a minute
    run(w, clock, 25)  # a.png appeared at 10 s: its batch goes at 70 s
    assert fake.reads == [["a.png"]]
    png(folder / "b.png")
    run(w, clock, 30)
    assert fake.reads == [["a.png"], ["b.png"]]


def test_a_growing_file_waits_until_it_settles(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=0))
    fake = Fake()
    w, clock = start(fake)
    big = folder / "video.mp4"
    for i in range(30):  # Drive still downloading: it grows every look
        with open(big, "ab") as f:
            f.write(b"x" * 100)
        w.tick()
        clock.t += watch.POLL
    assert fake.reads == []
    assert watch.read_status()["message"] == "Waiting for 1 file to finish downloading"
    run(w, clock, 90)
    assert fake.reads == [["video.mp4"]]


def test_hidden_temporary_and_other_files_are_ignored(folder):
    for n in (".hidden.png", "~$x.png", "notes.txt", "part.tmp"):
        (folder / n).write_bytes(b"x")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 600)
    assert fake.reads == []


def test_keep_order_numbers_a_numbered_set(folder):
    for n in ("1.png", "2.png", "3.png"):
        png(folder / n)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["01 Name 1.png", "02 Name 2.png", "03 Name 3.png"]


def test_name_clash_gets_a_number_and_overwrites_nothing(folder):
    png(folder / "Name a.png", "blue")
    known.record_folder(folder)
    png(folder / "a.png")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["Name a (2).png", "Name a.png"]


def test_file_changed_between_reading_and_renaming_is_read_again(folder):
    png(folder / "a.png")
    fake = Fake()

    def change():
        if len(fake.reads) == 1:
            with open(folder / "a.png", "ab") as f:
                f.write(b"more")

    fake.during_read = change
    w, clock = start(fake)
    run(w, clock, 300)
    assert len(fake.reads) == 2 and files(folder) == ["Name a.png"]


def test_file_deleted_mid_batch_does_not_stop_the_rest(folder):
    png(folder / "a.png")
    png(folder / "b.png", "blue")
    fake = Fake(during_read=lambda: (folder / "a.png").unlink())
    w, clock = start(fake)
    run(w, clock, 300)
    assert files(folder) == ["Name b.png"]
    assert fake.said[-1] == "1 file renamed and ready for ProPresenter: Name b."


def test_big_drops_go_in_batches(folder, monkeypatch):
    monkeypatch.setattr(watch, "MAX_BATCH", 2)
    for n in ("a.png", "b.png", "c.png"):
        png(folder / n)
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 300)
    assert fake.reads == [["a.png", "b.png"], ["c.png"]]


def test_turning_watching_off_stops_it(folder):
    w, clock = start(Fake())
    assert w.tick() is True
    config.save(watch=dict(config.watch_settings(), enabled=False))
    assert w.tick() is False and watch.read_status()["state"] == "stopped"


def test_a_new_folder_starts_afresh(folder, tmp_path):
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 200)
    other = tmp_path / "Other"
    other.mkdir()
    png(other / "x.png")
    config.save(watch=dict(config.watch_settings(), folder=str(other)))
    run(w, clock, 100)
    assert fake.reads == [["x.png"]] and files(other) == ["Name x.png"]


def test_spend_is_kept_per_month_in_its_own_file(folder):
    watch.record_spend(0.5)
    watch.record_spend(0.25)
    assert watch.spent_month() == pytest.approx(0.75)
    data = json.loads((watch.watch_dir() / "spend.json").read_text())
    assert data == {time.strftime("%Y-%m"): 0.75}
    assert "config.json" not in [p.name for p in watch.watch_dir().iterdir()]


def test_log_rolls_over(monkeypatch):
    monkeypatch.setattr(watch, "LOG_LIMIT", 100)
    for i in range(20):
        watch.log("line %d" % i)
    assert (watch.watch_dir() / "watch.log.1").exists()
    assert (watch.watch_dir() / "watch.log").stat().st_size < 200


def test_text_helpers():
    assert watch._done_text(["A", "B", "C", "D", "E"], []) == \
        "5 files renamed and ready for ProPresenter: A, B, C and 2 more."
    assert watch._done_text(["A"] * 11, ["7.png"]) == \
        "11 files renamed and ready for ProPresenter. 1 couldn't be named yet: 7.png"
    assert watch._done_text([], ["7.png", "8.png"]) == "2 files couldn't be named yet: 7.png, 8.png"
    assert watch._dollars(5.0) == "US$5" and watch._dollars(2.5) == "US$2.50"
    t = time.mktime((2026, 10, 11, 8, 4, 0, 0, 0, -1))
    assert watch._clock_text(t) == "8:04am"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_watch.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'watch'`).

- [ ] **Step 3: Implement** (`watch.py`; the failure and cost parts of `Watcher` are written here too and tested in Task 7)

```python
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
        """Start afresh on the current folder's new files."""
        self.seen = {}  # path -> {"print", "since"}: each new file and when it last changed
        self.activity = self.clock()  # when a new file last appeared or changed
        self.descs = {}  # print -> description already paid for
        self.failures = {}  # print -> {"count", "paid", "next"}
        self.given_up = set()  # prints left alone until the next start-up

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
        settling = [p for p, e in self.seen.items() if p not in ready and e["print"] not in self.given_up
                    and not self._later(e["print"], now)]
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

    def _later(self, f, now):
        fail = self.failures.get(f)
        return bool(fail and fail["next"] > now)

    def _ready(self, now):
        out = [p for p, e in self.seen.items()
               if e["print"] not in self.given_up and now - e["since"] >= SETTLE
               and not self._later(e["print"], now) and _opens(p)]
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
        prints = [self.seen[p]["print"] for p in paths]
        items = [{"id": i, "path": str(p), "name": p.name, "kind": scanner.kind(p)} for i, p in enumerate(paths)]
        self.say("Renaming %s…" % _plural(len(items), "new file"))
        self._status("renaming", "Renaming %s…" % _plural(len(items), "file"))
        log("Batch: " + ", ".join(p.name for p in paths))
        failed, refused = {}, None  # failed: print -> whether a paid request failed for it
        todo = [(it, f) for it, f in zip(items, prints) if f not in self.descs]
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
        described = [(it, f) for it, f in zip(items, prints) if f in self.descs]
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
        names = {f: it["name"] for it, f in zip(items, prints)}
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
        """Rename the named files. Returns {print: final name} for each file now ready."""
        nums = scanner.order_numbers(items) if scanner.looks_numbered(items) else None
        planned, wanted = {}, []
        for (it, f), r in zip(described, results):
            try:
                changed = known.fingerprint(it["path"]) != f
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
        known.add(self.folder, [(Path(moved.get(p, p)).name, f) for p, f in planned.items() if f in done])
        for f in done:
            self.descs.pop(f, None)
            self.failures.pop(f, None)
        return done

    def _failed(self, f, paid, now):
        """Count a failure. Returns True when the file is now left alone until the next start-up."""
        e = self.failures.setdefault(f, {"count": 0, "paid": 0, "next": 0.0})
        e["count"] += 1
        e["paid"] += bool(paid)
        if e["paid"] >= PAID_TRIES or e["count"] > len(RETRY):
            self.given_up.add(f)
            self.descs.pop(f, None)
            return True
        e["next"] = now + RETRY[e["count"] - 1]
        return False
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_watch.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add watch.py tests/test_watch.py
git commit -m "feat: background renaming watcher: new files, batches, renaming, status and log"
```

---

### Task 7: The watcher: failures and cost

**Files:**
- Modify: `watch.py` only if a test below fails
- Test: `tests/test_watch_failures.py`

**Interfaces:**
- Consumes: everything Task 6 produces.

- [ ] **Step 1: Write the tests** (`tests/test_watch_failures.py`)

```python
import json
import time

import pytest

import config
import known
import namer
import watch
from test_watch import Clock, Fake, files, png, run, start


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "Sunday Media"
    d.mkdir()
    config.save(key="sk-test", watch={"enabled": True, "folder": str(d), "startup_wait_min": 0})
    known.record_folder(d)
    png(d / "welcome.png")
    return d


def test_failed_naming_reruns_naming_only_and_never_renames_with_a_guess(folder):
    fake = Fake(fail_name=1)
    w, clock = start(fake)
    run(w, clock, 90)
    assert files(folder) == ["welcome.png"] and len(fake.reads) == 1 and len(fake.names) == 1
    assert fake.said[-1] == "1 file couldn't be named yet: welcome.png"
    run(w, clock, 300)
    assert len(fake.reads) == 1 and len(fake.names) == 2  # paid descriptions kept: naming only
    assert files(folder) == ["Name welcome.png"]


def test_two_paid_failures_leave_the_file_until_the_next_start_up(folder):
    fake = Fake(fail_name=5)
    w, clock = start(fake)
    run(w, clock, 3600)
    assert len(fake.names) == 2 and files(folder) == ["welcome.png"]
    assert fake.said[-1] == "Couldn't name welcome.png. It's still in Sunday Media under its old name."
    w2, clock = start(fake, clock)  # the next start-up tries again
    run(w2, clock, 90)
    assert len(fake.names) == 3


def test_a_file_the_model_cannot_read_counts_as_paid(folder):
    fake = Fake(fail_read={"welcome.png"})
    w, clock = start(fake)
    run(w, clock, 3600)
    assert len(fake.reads) == 2 and fake.names == []
    assert "Couldn't name welcome.png" in fake.said[-1]


def test_a_file_that_cannot_be_opened_here_is_tried_three_times(folder):
    fake = Fake(local={"welcome.png"})
    w, clock = start(fake)
    run(w, clock, 90)
    assert len(fake.reads) == 1
    run(w, clock, 300)
    assert len(fake.reads) == 2
    run(w, clock, 1800)
    assert len(fake.reads) == 3 and "Couldn't name welcome.png" in fake.said[-1]
    run(w, clock, 3600)
    assert len(fake.reads) == 3


def test_free_check_failure_sends_nothing_and_checks_again_later(folder):
    fake = Fake(check="connection")
    w, clock = start(fake)
    run(w, clock, 120)
    assert fake.reads == [] and fake.checks == 1
    assert fake.said[-1] == watch.PROBLEMS["connection"]
    assert watch.read_status()["message"] == "Paused: can't reach OpenRouter"
    run(w, clock, 240)
    assert fake.checks == 1  # every 5 minutes, not every look
    fake.check_result = None
    run(w, clock, 60)
    assert fake.checks == 2 and files(folder) == ["Name welcome.png"]
    assert fake.said.count(watch.PROBLEMS["connection"]) == 1


def test_out_of_credit_is_said_once_and_checked_every_15_minutes(folder):
    fake = Fake(check="credit")
    w, clock = start(fake)
    run(w, clock, 965)  # first check at 60 s, the next one 15 minutes later
    assert fake.checks == 2 and fake.reads == []
    assert fake.said.count(watch.PROBLEMS["credit"]) == 1


def test_a_refused_request_costs_no_attempt(folder):
    fake = Fake(refuse=402)
    w, clock = start(fake)
    run(w, clock, 90)
    assert len(fake.reads) == 1 and w.failures == {} and watch.PROBLEMS["credit"] in fake.said
    fake.refuse = None
    run(w, clock, 900)
    assert files(folder) == ["Name welcome.png"]


def test_a_problem_is_said_again_after_it_cleared_and_came_back(folder):
    fake = Fake(check="connection")
    w, clock = start(fake)
    run(w, clock, 90)
    fake.check_result = None
    run(w, clock, 300)
    png(folder / "giving.png", "blue")
    fake.check_result = "connection"
    run(w, clock, 60)
    assert fake.said.count(watch.PROBLEMS["connection"]) == 2


def test_monthly_limit_pauses_until_raised(folder):
    config.write_json(watch.watch_dir() / "spend.json", {time.strftime("%Y-%m"): 5.0})
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 120)
    assert fake.reads == [] and fake.checks == 0
    assert fake.said[-1] == "Background renaming has reached this month's US$5 limit. Raise it in Settings to carry on."
    assert watch.read_status()["message"] == "Paused: this month's US$5 limit is reached"
    config.save(watch=dict(config.watch_settings(), monthly_limit_usd=10))
    run(w, clock, 30)
    assert files(folder) == ["Name welcome.png"]


def test_no_key_pauses(folder, monkeypatch):
    monkeypatch.delenv("SMART_EXPLORER_MOCK", raising=False)
    config.save(key="")
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 120)
    assert fake.reads == [] and fake.said[-1] == watch.PROBLEMS["nokey"]


def test_test_mode_names_without_a_key(folder, monkeypatch):
    monkeypatch.setenv("SMART_EXPLORER_MOCK", "1")
    config.save(key="")
    w = watch.Watcher(clock=Clock(), say=lambda t: None)
    clock = w.clock
    run(w, clock, 120)
    assert files(folder) == ["Slide 1.png"]


def test_missing_folder_is_said_after_the_wait_and_grace(folder):
    config.save(watch=dict(config.watch_settings(), startup_wait_min=3, folder=str(folder.parent / "Gone")))
    fake = Fake()
    w, clock = start(fake)
    run(w, clock, 295)
    assert fake.said == ["Smart Explorer is watching Gone. New files will be renamed in 3 minutes."]
    assert watch.read_status()["message"] == "Waiting for Gone to appear"
    run(w, clock, 60)
    assert fake.said[-1] == "Smart Explorer can't find Gone. Check Google Drive is running and signed in."
    run(w, clock, 600)
    assert fake.said.count(fake.said[-1]) == 1


def test_folder_that_comes_back_resumes(folder):
    fake = Fake()
    w, clock = start(fake)
    hidden = folder.with_name("Sunday Media (signed out)")
    folder.rename(hidden)
    run(w, clock, 300)
    assert watch.PROBLEMS["folder"].format(folder="Sunday Media") in fake.said
    hidden.rename(folder)
    run(w, clock, 120)
    assert files(folder) == ["Name welcome.png"]


def test_free_check_reads_key_and_credit(monkeypatch):
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": False, "error": "x", "status": 401})
    assert watch.free_check("k") == "key"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": False, "error": "x", "status": 402})
    assert watch.free_check("k") == "credit"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": False, "error": "x", "status": None})
    assert watch.free_check("k") == "connection"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": True, "left": 0.0})
    assert watch.free_check("k") == "credit"
    monkeypatch.setattr(namer, "check_key", lambda key: {"ok": True})
    monkeypatch.setattr(namer, "credits_left", lambda key: None)
    assert watch.free_check("k") is None
    monkeypatch.setattr(namer, "credits_left", lambda key: -0.01)
    assert watch.free_check("k") == "credit"
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_watch_failures.py -q`
Expected: all pass with Task 6's `watch.py`. Any failure is a bug in `watch.py`: fix it there (not in the test) so it matches the spec's "Failures and cost" section, then run again.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_watch_failures.py watch.py
git commit -m "test: background renaming failures, retries, free checks and the monthly limit"
```

---

### Task 8: Running the watcher as its own process

**Files:**
- Modify: `watch.py` (append), `desktop.py`
- Test: `tests/test_watch_process.py`

**Interfaces:**
- Consumes: `watch.Watcher`, `autostart.watch_command`.
- Produces: `watch.take_lock() -> file or None`; `watch.release(f)`; `watch.running() -> bool`; `watch.request_stop()`; `watch.stop_and_wait(timeout=10.0, sleep=time.sleep) -> bool`; `watch.spawn(popen=subprocess.Popen)`; `watch.main(sleep=time.sleep, watcher=None) -> int`; `desktop.main(argv=None)` handles `--watch`.

- [ ] **Step 1: Write the failing tests** (`tests/test_watch_process.py`)

```python
import subprocess
import sys

import autostart
import config
import desktop
import watch


def test_only_one_watcher_holds_the_lock():
    assert not watch.running()
    f = watch.take_lock()
    assert f is not None and watch.take_lock() is None and watch.running()
    watch.release(f)
    assert not watch.running()


def test_main_returns_at_once_when_another_watcher_runs():
    f = watch.take_lock()
    ticks = []

    class W:
        def tick(self):
            ticks.append(1)
            return True

    assert watch.main(sleep=lambda s: None, watcher=W()) == 0 and ticks == []
    watch.release(f)


def test_main_stops_when_watching_is_off(tmp_path):
    config.save(watch={"enabled": False})
    assert watch.main(sleep=lambda s: None) == 0
    assert not watch.running()


def test_the_stop_file_stops_main(tmp_path):
    config.save(watch={"enabled": True, "folder": str(tmp_path), "startup_wait_min": 0})
    watch.request_stop()  # left over from before: must not stop the new watcher
    looks = []

    def sleep(s):
        looks.append(1)
        if len(looks) == 3:
            watch.request_stop()

    watch.main(sleep=sleep, watcher=watch.Watcher(say=lambda t: None))
    assert len(looks) == 3 and watch.read_status()["state"] == "stopped"
    assert not (watch.watch_dir() / "stop").exists()


def test_main_survives_an_error_in_one_tick():
    calls = []

    class W:
        def tick(self):
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError("folder locked")
            return False

    assert watch.main(sleep=lambda s: None, watcher=W()) == 0 and len(calls) == 2
    assert "folder locked" in (watch.watch_dir() / "watch.log").read_text("utf-8")


def test_stop_and_wait(monkeypatch):
    assert watch.stop_and_wait() is True  # nothing running
    f = watch.take_lock()
    assert watch.stop_and_wait(timeout=0.5, sleep=lambda s: None) is False
    assert (watch.watch_dir() / "stop").exists()
    watch.release(f)


def test_spawn_starts_the_watch_command_detached(monkeypatch):
    seen = {}
    watch.request_stop()
    watch.spawn(popen=lambda argv, **kw: seen.update(argv=argv, kw=kw))
    assert seen["argv"] == autostart.watch_command()
    assert seen["kw"]["stdout"] == subprocess.DEVNULL
    assert ("start_new_session" in seen["kw"]) == (sys.platform != "win32")
    assert not (watch.watch_dir() / "stop").exists()


def test_desktop_watch_flag_runs_the_watcher(monkeypatch):
    monkeypatch.setattr(watch, "main", lambda: 7)
    assert desktop.main(["--watch"]) == 7
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_watch_process.py -q`
Expected: FAIL (`AttributeError: module 'watch' has no attribute 'take_lock'`).

- [ ] **Step 3: Implement**

Append to `watch.py`:

```python
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
    popen(autostart.watch_command(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, close_fds=True, **kw)


def main(sleep=time.sleep, watcher=None):
    """Watch until stopped or switched off. Returns at once when another watcher runs."""
    lock = take_lock()
    if lock is None:
        return 0
    _take_stop()
    w = watcher or Watcher()
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
```

In `desktop.py` add `import sys` and make `main` take argv:

```python
def main(argv=None):
    if "--watch" in (sys.argv[1:] if argv is None else argv):
        import watch  # background renaming: no window, no web server
        return watch.main()
    url = serve()
```

(the rest of `main` is unchanged).

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add watch.py desktop.py tests/test_watch_process.py
git commit -m "feat: --watch runs background renaming as its own process, one at a time, stoppable"
```

---

### Task 9: The window's API for watching

**Files:**
- Modify: `app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `watch.running`, `watch.spawn`, `watch.request_stop`, `watch.read_status`, `watch.spending`, `watch.spent_month`, `watch.watch_dir`, `known.record_folder`, `known.visible`, `known.add_paths`, `known.same_folder`, `autostart.available/enable/disable`, `config.watch_settings`.
- Produces: `GET /api/watch` → `{"settings", "running", "status", "spent_month", "can_autostart"}`; `POST /api/watch/preview {folder}` → `{"count"}`; `POST /api/watch {enabled?, folder?, profile?, startup_wait_min?, monthly_limit_usd?, autostart?}` → same as GET (+ `"error"` when start-up could not be set); `POST /api/watch/start`; `POST /api/watch/log`. `/api/status` spend totals include background spend.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_app.py`)

```python
@pytest.fixture
def watcher(monkeypatch):
    import autostart
    import watch
    calls = {"spawn": 0, "stop": 0, "running": False, "auto": []}
    monkeypatch.setattr(watch, "running", lambda: calls["running"])
    monkeypatch.setattr(watch, "spawn", lambda: calls.__setitem__("spawn", calls["spawn"] + 1))
    monkeypatch.setattr(watch, "request_stop", lambda: calls.__setitem__("stop", calls["stop"] + 1))
    monkeypatch.setattr(autostart, "available", lambda system=None: True)
    monkeypatch.setattr(autostart, "enabled", lambda: False)
    monkeypatch.setattr(autostart, "enable", lambda: calls["auto"].append("on"))
    monkeypatch.setattr(autostart, "disable", lambda: calls["auto"].append("off"))
    return calls


def test_watch_starts_off(client, watcher):
    w = client.get("/api/watch").get_json()
    assert w["settings"] == config.WATCH_DEFAULTS and w["running"] is False and w["spent_month"] == 0
    assert w["can_autostart"] is True and w["status"] == {}


def test_watch_preview_counts_what_would_be_left_alone(client, watcher, folder):
    assert client.post("/api/watch/preview", json={"folder": str(folder)}).get_json() == {"count": 2}
    assert client.post("/api/watch/preview", json={"folder": "relative"}).status_code == 400


def test_turning_watching_on_records_the_folder_and_starts(client, watcher, folder):
    import known
    w = client.post("/api/watch", json={"enabled": True, "folder": str(folder), "startup_wait_min": 5,
                                        "monthly_limit_usd": 8, "autostart": True}).get_json()
    assert w["settings"]["enabled"] is True and w["settings"]["startup_wait_min"] == 5
    assert known.new_files(folder) == []  # what was there is left alone
    assert watcher["spawn"] == 1 and watcher["auto"] == ["on"]
    watcher["running"] = True
    client.post("/api/watch", json={"monthly_limit_usd": 9})
    assert watcher["spawn"] == 1  # already running
    client.post("/api/watch", json={"enabled": False})
    assert watcher["stop"] == 1 and watcher["auto"][-1] == "off"


def test_watching_a_missing_folder_is_refused(client, watcher, tmp_path):
    r = client.post("/api/watch", json={"enabled": True, "folder": str(tmp_path / "nope")})
    assert r.status_code == 400 and not config.watch_settings()["enabled"]


def test_start_button_starts_a_stopped_watcher(client, watcher, folder):
    client.post("/api/watch/start", json={})
    assert watcher["spawn"] == 0  # watching is off
    client.post("/api/watch", json={"enabled": True, "folder": str(folder)})
    client.post("/api/watch/start", json={})
    assert watcher["spawn"] == 2


def test_spend_totals_include_background_renaming(client, watcher):
    import watch
    watch.record_spend(0.4)
    s = client.get("/api/status").get_json()
    assert s["spent_month"] == pytest.approx(0.4) and s["spent_total"] == pytest.approx(0.4)
    assert client.get("/api/watch").get_json()["spent_month"] == pytest.approx(0.4)


def test_window_renames_in_the_watched_folder_become_known(client, watcher, folder):
    import known
    client.post("/api/watch", json={"enabled": True, "folder": str(folder)})
    Image.new("RGB", (40, 20), "green").save(folder / "c.png")
    client.post("/api/rename", json={"items": [{"path": str(folder / "c.png"), "new_name": "Giving"}]})
    assert known.new_files(folder) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_app.py -q -k "watch or background"`
Expected: FAIL (404s for `/api/watch`).

- [ ] **Step 3: Implement** (in `app.py`)

Add imports `import subprocess`, `import sys`, `import autostart`, `import known`, `import watch`. Change `status()`'s spend lines:

```python
def status():
    c = config.load()
    spend, background = spending(c), watch.spending()
    month = time.strftime("%Y-%m")
    return {...,  # every other key unchanged
            "spent_month": round(spend.get(month, 0.0) + background.get(month, 0.0), 6),
            "spent_total": round(sum(spend.values()) + sum(background.values()), 6)}
```

In `api_rename`, after `out = renamer.apply(pairs)`:

```python
    w = config.watch_settings()
    if w["enabled"] and w["folder"]:  # renamed here, so background renaming leaves them alone
        known.add_paths(w["folder"], [new for _, new in pairs[:out["renamed"]]])
```

Add the endpoints:

```python
def watch_state():
    return {"settings": config.watch_settings(), "running": watch.running(), "status": watch.read_status(),
            "spent_month": round(watch.spent_month(), 6), "can_autostart": autostart.available()}


def _is_folder(f):
    return isinstance(f, str) and bool(f) and Path(f).is_absolute() and Path(f).is_dir()


@app.get("/api/watch")
def api_watch():
    return jsonify(watch_state())


@app.post("/api/watch/preview")
def api_watch_preview():
    folder = (request.get_json(silent=True) or {}).get("folder")
    if not _is_folder(folder):
        return jsonify(error=NOT_FOUND), 400
    return jsonify(count=len(known.visible(folder)))


@app.post("/api/watch")
def api_watch_save():
    """Save the Watch a folder settings, then start or stop background renaming to
    match. Turning it on, or changing the folder, records the files already there,
    which are then left as they are."""
    body = request.get_json(silent=True) or {}
    old = config.watch_settings()
    new = dict(old)
    for k in ("enabled", "autostart"):
        if isinstance(body.get(k), bool):
            new[k] = body[k]
    if isinstance(body.get("folder"), str):
        new["folder"] = body["folder"].strip()
    if body.get("profile") in conventions.PROFILES:
        new["profile"] = body["profile"]
    for k in ("startup_wait_min", "monthly_limit_usd"):
        if isinstance(body.get(k), (int, float)) and not isinstance(body.get(k), bool):
            new[k] = body[k]
    if new["enabled"]:
        if not _is_folder(new["folder"]):
            return jsonify(error=NOT_FOUND), 400
        if not old["enabled"] or not known.same_folder(old["folder"], new["folder"]):
            known.record_folder(new["folder"])
    with LOCK:
        config.save(watch=new)
    new = config.watch_settings()
    err = None
    if new["enabled"] and new["autostart"] and autostart.available():
        err = autostart.enable()  # also refreshes the shortcut after the app moved
    else:
        autostart.disable()
    if new["enabled"] and not watch.running():
        watch.spawn()
    elif not new["enabled"] and watch.running():
        watch.request_stop()
    out = watch_state()
    if err:
        out["error"] = err
    return jsonify(out)


@app.post("/api/watch/start")
def api_watch_start():
    if config.watch_settings()["enabled"] and not watch.running():
        watch.spawn()
    return jsonify(watch_state())


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
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: the window's API for background renaming: settings, start, stop, status, log"
```

---

### Task 10: Status bar and "Watch a folder" in Settings

**Files:**
- Modify: `static/index.html`, `static/app.js`, `static/style.css`
- Test: manual, in the browser pane, against a throwaway home folder

**Interfaces:**
- Consumes: Task 9's endpoints.

- [ ] **Step 1: Markup** (`static/index.html`)

After the `#update` bar:

```html
<div id="watchbar" class="watchbar" role="status" hidden>
  <span class="dot" aria-hidden="true"></span>
  <span id="watchText"></span>
  <span class="spacer"></span>
  <button id="watchStart" class="primary" hidden>Start</button>
</div>
```

In the Settings dialog, after the `.styles` block and before `#keymsg`:

```html
    <fieldset class="watch">
      <legend>Watch a folder</legend>
      <label class="check"><input id="wOn" type="checkbox"><span>Rename new files in a folder by itself, with no window open</span></label>
      <div id="wFields">
        <label>Folder <small>The Google Drive folder ProPresenter's playlist watches. Files already in it are left as they are.</small>
          <span class="keyrow"><input id="wFolder" type="text" spellcheck="false" placeholder="Paste the folder's path, or Choose">
            <button type="button" id="wPick">Choose</button></span>
        </label>
        <label>Naming style <select id="wProfile"></select></label>
        <div class="pair">
          <label>Start-up wait (minutes) <small>Time for Google Drive to bring new files down.</small>
            <input id="wWait" type="number" min="0" max="30" step="1"></label>
          <label>Monthly limit (US$) <small id="wSpent"></small>
            <input id="wLimit" type="number" min="0" step="1"></label>
        </div>
        <label class="check" id="wAutoRow"><input id="wAuto" type="checkbox"><span>Start when Windows starts</span></label>
        <p class="wstatus"><span id="wStatus"></span> <button type="button" id="wLog" class="link">Open log</button></p>
      </div>
    </fieldset>
```

- [ ] **Step 2: Styles** (append to `static/style.css`, before the `prefers-reduced-motion` block)

```css
/* ---------- background renaming ---------- */
.watchbar {
  display: flex; align-items: center; gap: 10px; padding: 7px 24px;
  background: var(--ok-soft); border-bottom: 1px solid #abefc6; font-size: 13.5px; color: var(--ink-2);
}
.watchbar .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--ok); }
.watchbar.problem { background: var(--err-soft); border-bottom-color: #fecdca; }
.watchbar.problem .dot { background: var(--err); }
.watchbar button { padding: 6px 12px; }
dialog fieldset.watch { margin: 0 0 16px; padding: 10px 14px 2px; border: 1px solid var(--line); border-radius: var(--r-sm); }
dialog fieldset.watch legend { padding: 0 6px; font-size: 13px; font-weight: 600; color: var(--ink-2); }
dialog label.check { display: flex; margin-bottom: 12px; padding: 8px 12px; font-size: 13px; }
dialog label.check input { display: inline-block; width: 16px; margin: 0; }
dialog .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
#wFields { padding-top: 4px; }
.wstatus { margin: 0 0 12px; font-size: 13px; color: var(--mute); }
```

- [ ] **Step 3: Behaviour** (`static/app.js`)

Add the new ids to the `els` list: `"watchbar", "watchText", "watchStart", "wOn", "wFields", "wFolder", "wPick", "wProfile", "wWait", "wLimit", "wSpent", "wAutoRow", "wAuto", "wStatus", "wLog"`.

Add this block after the Updates section:

```js
// Background renaming (Settings, Watch a folder). Settings sets it up; the bar under
// the header says what it is doing, read from the background copy's status file.
let watchState = null, watchTimer = 0;

function watchLine(w) {
  if (!w.running) return "Background renaming isn't running.";
  return (w.status && w.status.state !== "stopped" && w.status.message) || "Starting…";
}

function showWatch(w) {
  watchState = w;
  const on = w.settings.enabled;
  els.watchbar.hidden = !on;
  els.watchbar.classList.toggle("problem", on && (!w.running || (w.status || {}).state === "paused"));
  els.watchText.textContent = on ? watchLine(w) : "";
  els.watchStart.hidden = !on || w.running;
  els.wStatus.textContent = on ? watchLine(w) : "";
  clearTimeout(watchTimer);
  if (on) watchTimer = setTimeout(refreshWatch, 5000);
}

async function refreshWatch() {
  try { showWatch(await api("watch")); } catch (e) { /* the app is closing */ }
}

function fillWatch() {
  const w = watchState;
  if (!w) return;
  const s = w.settings;
  els.wOn.checked = s.enabled;
  els.wFolder.value = s.folder;
  els.wProfile.innerHTML = "";
  for (const p of status.profiles) els.wProfile.add(new Option(p.label, p.id));
  els.wProfile.value = s.profile;
  els.wWait.value = s.startup_wait_min;
  els.wLimit.value = s.monthly_limit_usd;
  els.wSpent.textContent = `${dollars(w.spent_month)} spent this month in the background.`;
  els.wAutoRow.hidden = !w.can_autostart;
  els.wAuto.checked = s.autostart;
  els.wStatus.textContent = s.enabled ? watchLine(w) : "";
  els.wFields.hidden = !els.wOn.checked;
}

function watchDraft() {
  return {
    enabled: els.wOn.checked, folder: els.wFolder.value.trim(), profile: els.wProfile.value,
    startup_wait_min: Math.round(Number(els.wWait.value) || 0), monthly_limit_usd: Number(els.wLimit.value) || 0,
    autostart: els.wAuto.checked,
  };
}

// Saves Watch a folder when it changed. Returns false when the user backed out.
async function saveWatch() {
  if (!watchState) return true;
  const d = watchDraft(), s = watchState.settings;
  if (!Object.keys(d).some((k) => d[k] !== s[k])) return true;
  if (d.enabled && (!s.enabled || d.folder !== s.folder)) {
    const { count } = await api("watch/preview", { folder: d.folder });
    const msg = `Smart Explorer will rename new files in this folder by itself, even with this window closed.\n\n`
      + `${plural(count, "file")} already in it will be left as they are.`;
    if (!confirm(msg)) return false;
  }
  const w = await api("watch", d);
  showWatch(w);
  if (w.error) throw new Error(w.error);
  return true;
}
```

Change `saveSettings` to save the watch settings first:

```js
async function saveSettings() {
  if (!(await saveWatch())) return;
  const body = { model: els.model.value || els.custom.value.trim() || status.model };
  if (els.key.value.trim()) body.key = els.key.value.trim();
  status = await api("settings", body);
  fillSettings();
  els.settings.close();
  toast("Settings saved");
}
```

Replace the gear handler and the Save handler, and add the new handlers next to them:

```js
els.gear.onclick = async () => {
  fillSettings();
  try { watchState = await api("watch"); } catch (e) { /* shown as before, without the watch section filled */ }
  fillWatch();
  els.settings.showModal();
};
```

```js
els.save.onclick = inDialog(els.keymsg, saveSettings);  // a folder that can't be found is said in the dialog
els.wOn.onchange = () => (els.wFields.hidden = !els.wOn.checked);
els.wPick.onclick = inDialog(els.keymsg, async () => {
  const { folder } = await api("pick-folder");
  if (folder) els.wFolder.value = folder;
});
els.wLog.onclick = inDialog(els.keymsg, () => api("watch/log", {}));
els.watchStart.onclick = guarded(async () => showWatch(await api("watch/start", {})));
```

In the start-up block at the end, after the update check:

```js
  api("watch").then(showWatch).catch(() => {});
```

- [ ] **Step 4: Check it in the browser pane**

Run from source with a throwaway home folder, so the real `~/.smart-explorer` is not touched:

```bash
mkdir -p /tmp/se-ui-home/Sunday\ Media
HOME=/tmp/se-ui-home SMART_EXPLORER_MOCK=1 SMART_EXPLORER_HEADLESS=1 SMART_EXPLORER_PORT=8790 .venv/bin/python desktop.py
```

Open `http://127.0.0.1:8790` in the browser pane and check:
1. Settings shows the "Watch a folder" box; ticking it shows the fields; Windows start-up is hidden on a Mac.
2. Paste `/tmp/se-ui-home/Sunday Media`, wait 0, Save: the confirm says how many files are left alone; the green bar appears and moves from "Starting…" to "Watching Sunday Media".
3. Copy two images into the folder: within about 90 s they are renamed (`01 Slide 1.png`…) and the bar shows "last batch".
4. A folder that does not exist shows "Can't find that folder…" inside the dialog.
5. Turning it off hides the bar; the background copy exits (bar gone, `watch/lock` free).
6. No console errors (`read_console_messages`).

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat: status bar and Watch a folder settings for background renaming"
```

---

### Task 11: Updates, installer and a built-app check

**Files:**
- Modify: `updater.py`, `packaging/windows-installer.iss`, `.github/workflows/build.yml`
- Create: `scripts/smoke_watch.py`
- Test: `tests/test_updater.py`

**Interfaces:**
- Consumes: `watch.stop_and_wait`, `autostart.NAME`, `notify.APP_ID`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_updater.py`)

```python
def test_install_stops_background_renaming_first(monkeypatch, tmp_path):
    import watch
    order = []
    monkeypatch.setattr(updater, "download", lambda asset, folder, progress: tmp_path / "setup.exe")
    monkeypatch.setattr(watch, "stop_and_wait", lambda timeout=10.0: order.append("stop") or True)
    monkeypatch.setattr(updater, "launch", lambda installer, app: order.append("launch"))
    monkeypatch.setattr(updater.threading, "Timer", lambda *a, **k: type("T", (), {"start": lambda self: None})())
    updater._install({"size": 1}, tmp_path, "9.9.9")
    assert order == ["stop", "launch"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_updater.py -q -k background`
Expected: FAIL (`order == ["launch"]`).

- [ ] **Step 3: Implement**

`updater.py`: add `import watch` and, in `_install`, stop the watcher before launching the installer:

```python
        STATE["state"] = "installing"
        with LOCK:
            config.save(update_attempt=version)
        watch.stop_and_wait(timeout=10.0)  # Windows can't replace a running program; the installer starts it again
        launch(installer, app)
```

`packaging/windows-installer.iss`:

```
[Icons]
; The AppUserModelID lets background renaming's notifications carry the app's name and icon (notify.APP_ID).
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; AppUserModelID: "jimhoggey.SmartExplorer"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; An update started from inside the app runs Setup with /RELAUNCH=1: open the app again afterwards.
Filename: "{app}\{#AppName}.exe"; Flags: nowait; Check: Relaunch
; Background renaming starts with Windows (Settings, Watch a folder): start it again after an update.
Filename: "{app}\{#AppName}.exe"; Parameters: "--watch"; Flags: nowait; Check: WatchesAtStartup

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ""{#AppName}.exe"""; Flags: runhidden; RunOnceId: "StopSmartExplorer"

[UninstallDelete]
; autostart.NAME
Type: files; Name: "{userstartup}\Smart Explorer (background).lnk"

[Code]
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function WatchesAtStartup: Boolean;
begin
  Result := FileExists(ExpandConstant('{userstartup}\Smart Explorer (background).lnk'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { Background renaming has no window, so closing applications can miss it. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#AppName}.exe"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
```

`scripts/smoke_watch.py`:

```python
"""Check background renaming end to end: start the app with --watch on a throwaway
home folder (no key: SMART_EXPLORER_MOCK names files "Slide N"), drop two numbered
images into the watched folder, and wait for them to be renamed.

    python scripts/smoke_watch.py "dist/Smart Explorer/Smart Explorer.exe"
    python scripts/smoke_watch.py .venv/bin/python desktop.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image


def main(cmd):
    home = Path(tempfile.mkdtemp(prefix="se-watch-"))
    folder = home / "Sunday Media"
    folder.mkdir()
    cfg = home / ".smart-explorer"
    cfg.mkdir()
    (cfg / "config.json").write_text(json.dumps({"watch": {"enabled": True, "folder": str(folder), "startup_wait_min": 0}}))
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), SMART_EXPLORER_MOCK="1")
    proc = subprocess.Popen(cmd + ["--watch"], env=env)
    try:
        time.sleep(5)  # the folder starts empty, so these arrive as new files
        for n in ("1.png", "2.png"):
            Image.new("RGB", (64, 36), "red").save(folder / n)
        for _ in range(60):
            time.sleep(3)
            names = sorted(p.name for p in folder.iterdir())
            if names == ["01 Slide 1.png", "02 Slide 2.png"]:
                print("renamed:", names)
                (cfg / "watch" / "stop").write_text("stop")
                proc.wait(timeout=30)
                return 0
        print("not renamed:", sorted(p.name for p in folder.iterdir()))
        for name in ("status.json", "watch.log"):
            p = cfg / "watch" / name
            print(p.read_text("utf-8") if p.exists() else "%s missing" % name)
        return 1
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

`.github/workflows/build.yml`: after each job's "Smoke test the app" step add

```yaml
      - name: Smoke test background renaming (--watch renames new files)
        run: python scripts/smoke_watch.py "dist/Smart Explorer.app/Contents/MacOS/Smart Explorer"
```

(mac job) and

```yaml
      - name: Smoke test background renaming (--watch renames new files)
        shell: bash
        run: python scripts/smoke_watch.py "dist/Smart Explorer/Smart Explorer.exe"
```

(windows job), and add `"watch.py"`, `"known.py"`, `"notify.py"`, `"autostart.py"` and `"scripts/smoke_watch.py"` to the workflow's `pull_request.paths`.

- [ ] **Step 4: Run the suite and the end-to-end check from source**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

Run: `.venv/bin/python scripts/smoke_watch.py .venv/bin/python desktop.py`
Expected: `renamed: ['01 Slide 1.png', '02 Slide 2.png']`, exit code 0, within about 90 s.

- [ ] **Step 5: Commit**

```bash
git add updater.py packaging/windows-installer.iss .github/workflows/build.yml scripts/smoke_watch.py tests/test_updater.py
git commit -m "feat: updates stop and restart background renaming; installer and CI check it"
```

---

### Task 12: Docs

**Files:**
- Modify: `README.md`
- Create: `docs/background-renaming.md`
- Modify: `~/.claude/church/CHURCH.md` (outside the repo: projects table)

- [ ] **Step 1: README** — add a section after "Use":

```markdown
## Background renaming (watch a folder)

Smart Explorer can rename new files in one folder by itself, with no window open: made for a Google Drive folder that ProPresenter's playlist watches. Set it up in *Settings → Watch a folder*: the folder, the naming style, a start-up wait (minutes for Google Drive to bring new files down after the computer starts, default 3), a monthly spending limit for background naming (default US$5) and, on Windows, **Start when Windows starts**.

- Files already in the folder when you turn it on are left as they are. After that, a file is new when Smart Explorer knows neither its name nor its size and modified time: a file you rename by hand, or an updated slide uploaded under the same name, is not renamed again.
- It waits for each download to finish, names files that arrive together as one batch (Keep order numbering when they are numbered in sequence), and never renames with a guess: if naming fails, files keep their names and are tried again (at most twice per start-up, so a problem cannot keep spending).
- Before each batch it checks the key and credit with OpenRouter for free; out of credit or a rejected key pauses it until fixed.
- Windows notifications say when it starts, what it renamed and any problem. The window shows a status bar while watching is on. The log is in `~/.smart-explorer/watch/watch.log` (*Settings → Open log*).
- From source: `.venv/bin/python desktop.py --watch` runs it in the terminal.

For the people at the ProPresenter computer: [docs/background-renaming.md](docs/background-renaming.md).
```

- [ ] **Step 2: Volunteer page** — `docs/background-renaming.md`:

```markdown
# New slides and videos on the ProPresenter computer

Smart Explorer names new slides and videos for ProPresenter by itself. Files put in the shared Google Drive folder during the week arrive on this computer when it starts, get proper names, and appear in ProPresenter's playlist. You don't need to open anything.

## What you'll see after turning the computer on

1. **"Smart Explorer is watching Sunday Media…"** It has started. Wait a few minutes.
2. **"Renaming 12 new files…"**, then **"12 files renamed and ready for ProPresenter"**. Done: the files are in ProPresenter.
3. Or **"Checked Sunday Media: no new files."** Nothing new this week. That's fine.

## When a message says something is wrong

| Message says | What to do |
|---|---|
| can't find the folder | Check Google Drive is running (icon near the clock) and signed in. |
| can't reach the internet | Check the internet. It tries again by itself. |
| didn't accept the key, or out of credit | Tell the tech lead. The files keep their old names until it's fixed; they still work in ProPresenter. |
| reached this month's limit | Tell the tech lead. |
| couldn't name a file | That file keeps its old name. It's still usable. Rename it by hand in ProPresenter's folder if you like. |

Never rename or move files during a service.

## When you're stuck

Restart the computer. Still stuck: take a photo of the screen, write down what you tried, and message the tech lead.
```

- [ ] **Step 3: Church reference** — in `~/.claude/church/CHURCH.md`, "Projects and where their truth lives" table, add a row (no names, no versions):

```markdown
| Smart Explorer (`~/Claude/repos/apps/SmartExplorer-App`) | Names slides, videos and files with AI; background renaming watches the Google Drive folder ProPresenter uses (planned for the Windows PC; not yet checked on the rig) | README, `docs/` (volunteer page `docs/background-renaming.md`) |
```

- [ ] **Step 4: Run the whole suite once more**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/background-renaming.md
git commit -m "docs: background renaming in the README and a one-page volunteer note"
```
