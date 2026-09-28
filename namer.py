"""Two-stage naming via OpenRouter.

1. Read: vision requests of up to READ_BATCH files each, several in flight at once,
   report what is on every file. Each image goes at full resolution as its own
   image; the instructions are sent once per request, not once per file.
2. Name: one text request sees every description at once, so it can apply the
   convention consistently and tell similar files apart.

Cost is per token, not per request: running requests in parallel only saves time.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import conventions

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
KEY_URL = "https://openrouter.ai/api/v1/key"
HEADERS = {"Content-Type": "application/json", "HTTP-Referer": "https://smart-explorer.local", "X-Title": "Smart Explorer"}
# Reading a slide needs eyes, not deliberation; naming the batch needs some judgement.
READ_EFFORT, NAME_EFFORT = "low", "medium"
READ_BATCH = 8  # files per vision request
READ_WORKERS = 4  # vision requests in flight at once
CHUNK = 60  # files per naming request; bigger batches go in chunks that see the names already used
TEXT_LIMIT = 400  # characters of each file's text passed on to the naming step
NO_RETRY = (401, 402, 403)  # bad key, no credit, not allowed: retrying file by file cannot help

READ_ROLE = "You look at a numbered set of files and report what is on each one, so a later step can give each a good file name."
FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "n": {"type": "integer", "description": "The file's number, as labelled"},
        "category": {"type": "string", "description": "Best fitting category"},
        "subject": {"type": "string", "description": "The specific thing it is about: event, sermon series, song, Bible reference, business, place"},
        "text": {"type": "string", "description": "The readable words, at most about 40"},
        "visual": {"type": "string", "description": "The look in at most 8 words"},
        "date": {"type": "string", "description": "The most relevant date shown, as written, or empty"},
        "notes": {"type": "string", "description": "Anything else that matters for naming in at most 15 words, or empty"},
    },
    "required": ["n", "category", "subject", "text", "visual", "date", "notes"],
    "additionalProperties": False,
}
READ_SCHEMA = {"type": "object", "properties": {"files": {"type": "array", "items": FILE_SCHEMA}},
               "required": ["files"], "additionalProperties": False}
NAME_ROLE = "You name files. You get a description of every file in a batch and give each one a file name that follows the naming convention exactly."
NAME_SCHEMA = {
    "type": "object",
    "properties": {"names": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["i", "name"],
        "additionalProperties": False,
    }}},
    "required": ["names"],
    "additionalProperties": False,
}


class NamerError(Exception):
    def __init__(self, msg, status=None, cost=0.0):
        super().__init__(msg)
        self.status, self.cost = status, cost


def _request(url, key, data=None, timeout=90, tries=3):
    req = Request(url, data=data, headers={**HEADERS, "Authorization": "Bearer " + key})
    for attempt in range(tries):
        last = attempt == tries - 1
        try:
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            if last or not (e.code == 429 or e.code >= 500):
                body = e.read().decode(errors="replace")[:300]
                hint = " (pick another model in Settings)" if e.code in (400, 404) and "model" in body.lower() else ""
                raise NamerError("OpenRouter returned HTTP %s%s: %s" % (e.code, hint, body), status=e.code)
        except OSError as e:
            if last:
                raise NamerError("Could not reach OpenRouter: %s" % e)
        except ValueError:
            raise NamerError("OpenRouter returned invalid JSON")
        time.sleep(2 ** attempt)


def chat(key, model, messages, schema=None, effort=None, max_tokens=None, timeout=90):
    """Return (reply text, cost in USD as reported by OpenRouter)."""
    body = {"model": model, "messages": messages}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "reply", "strict": True, "schema": schema}}
    if effort:
        body["reasoning"] = {"effort": effort}
    if max_tokens:
        body["max_tokens"] = max_tokens
    data = _request(ENDPOINT, key, json.dumps(body).encode(), timeout)
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise NamerError("Unexpected reply from OpenRouter: %s" % json.dumps(data)[:200])
    cost = float((data.get("usage") or {}).get("cost") or 0)
    if not text:
        raise NamerError("Model returned an empty reply (%s)" % (choice.get("finish_reason") or "no text"), cost=cost)
    return text, cost


def parse_json(text):
    for m in re.finditer(r"[\[{]", text):
        try:
            return json.JSONDecoder().raw_decode(text, m.start())[0]
        except ValueError:
            pass
    raise NamerError("Model reply was not JSON: %s" % text[:100])


def _extras(context):
    return "\n\nContext for this batch from the user:\n" + context.strip() if context.strip() else ""


def read_prompt(profile, context=""):
    p = conventions.get(profile)
    return """%s

%s

Categories:
%s%s

Keep replies short, because every word the model writes costs more than a word it reads:
- text: the readable words, at most about 40. For documents, only the title, organisation, reference numbers, dates and totals.
- visual: at most 8 words. notes: at most 15 words, or empty.
Reply with JSON only: {"files": [{"n": <file number>, "category": "", "subject": "", "text": "", "visual": "", "date": "", "notes": ""}]}, one entry per file, in order.""" % (
        READ_ROLE, p["reader"], p["categories"], _extras(context))


def name_prompt(profile, context=""):
    p = conventions.get(profile)
    return """%s

%s%s

How to work:
- Base each name on what the file actually shows. Use the facts and context to fill gaps (series name, event, date, video length), never to invent content.
- Name the batch as a set: files of the same kind should read alike. Where files would otherwise get the same name, tell them apart by what actually differs between them, in their own words where possible.
- Every name must be different from every other name in the batch. already_used lists names that are taken: other files already in the same folders, and names given earlier in this batch. Never reuse one; if a file would get one, add a Detail from its own words to tell it apart.
- If a file's original name already follows the convention and matches its content, keep it.
- Reply with JSON only: {"names": [{"i": <the file's i>, "name": "<name without extension>"}]}, one entry per file.""" % (
        NAME_ROLE, p["rules"], _extras(context))


def _facts(item, encoded):
    return {"file": item["name"], "folder": Path(item["path"]).parent.name, "kind": item["kind"], **encoded.get("facts", {})}


def read_batch(key, model, items, encoded, profile=conventions.DEFAULT_PROFILE, context=""):
    """Describe several files in one request. Returns (descriptions in item order, cost).
    Each description carries its file's facts. Raises NamerError unless every file is described."""
    content = []
    for n, (item, enc) in enumerate(zip(items, encoded), 1):
        label = "File %d of %d. Facts: %s" % (n, len(items), json.dumps(_facts(item, enc)))
        if item["kind"] == "video" and len(enc["images"]) > 1:
            label += "\nThe next images are frames from early, middle and late in this video."
        content.append({"type": "text", "text": label})
        content += [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}} for b in enc["images"]]
        if enc.get("text"):
            content.append({"type": "text", "text": "Text layer of its first page:\n" + enc["text"]})
    content.append({"type": "text", "text": "Describe each of the %d files." % len(items)})
    text, cost = chat(key, model, [{"role": "system", "content": read_prompt(profile, context)},
                                   {"role": "user", "content": content}],
                      schema=READ_SCHEMA, effort=READ_EFFORT, max_tokens=1500 + 500 * len(items), timeout=180)
    try:
        got = parse_json(text)
        entries = got.get("files") if isinstance(got, dict) else got
        if not isinstance(entries, list):
            raise NamerError("Model reply had no list of files")
        entries = [e for e in entries if isinstance(e, dict)]
        by_n = {}
        for pos, e in enumerate(entries, 1):
            try:
                by_n[int(e.get("n", pos))] = e
            except (TypeError, ValueError):
                by_n[pos] = e
        described = sum(n in by_n for n in range(1, len(items) + 1))
        if described != len(items):
            raise NamerError("Model described %d of %d files" % (described, len(items)))
        if len(entries) != len(items):  # e.g. a video's frames described as extra files: numbering unreliable
            raise NamerError("Model returned %d descriptions for %d files" % (len(entries), len(items)))
    except NamerError as e:
        e.cost = cost
        raise
    return [dict({k: v for k, v in by_n[n].items() if k != "n"}, facts=_facts(item, enc))
            for n, (item, enc) in enumerate(zip(items, encoded), 1)], cost


def describe(key, model, item, encoded, profile=conventions.DEFAULT_PROFILE, context=""):
    """One file on its own. Returns (description, cost); a failure is {"error": ...}."""
    try:
        descs, cost = read_batch(key, model, [item], [encoded], profile, context)
        return descs[0], cost
    except Exception as e:
        return {"error": str(e)}, getattr(e, "cost", 0.0)


def _dedupe(names, taken=()):
    seen, out = {t.lower() for t in taken}, []
    for n in names:
        c, i = n, 2
        while c.lower() in seen:
            c, i = "%s (%d)" % (n, i), i + 1
        seen.add(c.lower())
        out.append(c)
    return out


def clean(name, original=""):
    """Tidy a proposed name: no extension, quotes, colons or slashes."""
    name = str(name or "").strip().strip("\"'`").strip()
    ext = Path(original).suffix
    if ext and name.lower().endswith(ext.lower()):
        name = name[: -len(ext)]
    name = re.sub(r"(?<=\d):(?=\d)", ".", name)  # John 3:16 -> John 3.16, 10:30 -> 10.30
    name = re.sub(r"\s+[/\\|]\s+", " - ", name)
    name = re.sub(r"[/\\|]", "-", name)  # 24/7 -> 24-7
    name = re.sub(r"(\s+-\s+)+", " - ", re.sub(r"\s+", " ", name))
    return name.strip(" -.")


def _for_naming(d):
    out = {k: v for k, v in d.items() if k not in ("error", "text")}
    out["text"] = str(d.get("text") or "")[:TEXT_LIMIT]
    return out


def _name_chunk(key, model, descs, used, prompt):
    payload = {"files": [_for_naming(d) for d in descs]}
    if used:
        payload["already_used"] = used
    text, cost = chat(key, model, [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload)}],
                      schema=NAME_SCHEMA, effort=NAME_EFFORT, max_tokens=16000, timeout=240)
    try:
        names = parse_json(text)
    except NamerError as e:
        e.cost = cost
        raise
    if isinstance(names, dict):
        names = names["names"] if isinstance(names.get("names"), list) else next((v for v in names.values() if isinstance(v, list)), None)
    if not isinstance(names, list):
        raise NamerError("expected a list of names, got %s" % type(names).__name__, cost=cost)
    by_i = {}
    for pos, n in enumerate(names):  # every entry: a duplicate must not push a real one out
        if isinstance(n, dict):
            i, n = n.get("i", n.get("index")), n.get("name")
            if i is None and pos < len(descs):
                i = descs[pos]["i"]
        else:  # a bare string lines up by position
            i = descs[pos]["i"] if pos < len(descs) else None
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if isinstance(n, str) and n.strip() and not by_i.get(i):
            by_i[i] = n
    got = [by_i.get(d["i"]) for d in descs]
    count = sum(isinstance(n, str) and bool(n.strip()) for n in got)
    if count != len(descs):
        raise NamerError("expected %d names, got %d" % (len(descs), count), cost=cost)
    return got, cost


def name_all(key, model, descs, profile=conventions.DEFAULT_PROFILE, context="", existing=()):
    """Return (names, error, cost). On failure names fall back to the file's own
    words and error explains why. The caller MUST surface it, or the batch looks fine.
    existing: names of other files already in the same folders, which new names must avoid."""
    err, names, cost = None, [], 0.0
    prompt = name_prompt(profile, context)
    try:
        for start in range(0, len(descs), CHUNK):
            got, c = _name_chunk(key, model, descs[start:start + CHUNK], list(existing) + [clean(n) for n in names], prompt)
            names += got
            cost += c
    except Exception as e:
        cost += getattr(e, "cost", 0.0)
        names = [None] * len(descs)
        err = "AI naming failed (%s). These are the raw words on each file, not chosen names." % e
    fallback = lambda d: clean(d.get("subject") or str(d.get("text") or "")[:60], d["original"]) or Path(d["original"]).stem
    return _dedupe((clean(n, d["original"]) or fallback(d) for n, d in zip(names, descs)), existing), err, cost


def number(items, names):
    """Prefix 01, 02... per folder in scan order, so ProPresenter imports keep the original order."""
    totals, seen, out = {}, {}, []
    for it in items:
        folder = str(Path(it["path"]).parent)
        totals[folder] = totals.get(folder, 0) + 1
    for it, n in zip(items, names):
        folder = str(Path(it["path"]).parent)
        seen[folder] = seen.get(folder, 0) + 1
        out.append("%0*d %s" % (max(2, len(str(totals[folder]))), seen[folder], n))
    return out


def run(key, model, items, encode, on_progress=None, profile=conventions.DEFAULT_PROFILE, context="",
        keep_order=False, existing=()):
    """Name every item. Returns {"results": [{id, path, proposed, error?}], "cost": USD}.
    existing: names already taken by other files in the same folders."""
    notify = on_progress or (lambda *a: None)
    opts = (profile, context)

    def read(batch):
        descs, cost, ready, enc = {}, 0.0, [], []
        for it in batch:
            try:
                enc.append(encode(it))
                ready.append(it)
            except Exception as e:
                descs[it["id"]] = {"error": "Could not read file: %s" % e}
        if ready:
            try:
                got, cost = read_batch(key, model, ready, enc, *opts)
                descs.update((it["id"], d) for it, d in zip(ready, got))
            except Exception as e:
                cost = getattr(e, "cost", 0.0)
                if len(ready) == 1 or getattr(e, "status", None) in NO_RETRY:
                    descs.update((it["id"], {"error": str(e)}) for it in ready)
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
    descs = [d for ds, _ in read_out for d in ds]
    ok = [{**d, "i": i, "original": it["name"]} for i, (it, d) in enumerate(zip(items, descs)) if "error" not in d]
    names, name_err, name_cost = name_all(key, model, ok, *opts, existing=existing) if ok else ([], None, 0.0)
    proposed = dict(zip((d["i"] for d in ok), names))
    chosen = [proposed.get(i, Path(it["name"]).stem) for i, it in enumerate(items)]
    if keep_order:
        chosen = number(items, chosen)
    out = []
    for it, d, name in zip(items, descs, chosen):
        r = {"id": it["id"], "path": it["path"], "proposed": name}
        if "error" in d:
            r["error"] = d["error"]
        elif name_err:
            r["error"] = name_err
        notify(it["id"], "named", name)
        out.append(r)
    return {"results": out, "cost": sum(c for _, c in read_out) + name_cost}


def check_key(key):
    try:
        return {"ok": True, "label": (_request(KEY_URL, key).get("data") or {}).get("label")}
    except NamerError as e:
        return {"ok": False, "error": str(e)}


def mock_run(items, on_progress=None, keep_order=False, **_):
    names = ["Slide %d" % i for i in range(1, len(items) + 1)]
    if keep_order:
        names = number(items, names)
    out = []
    for it, n in zip(items, names):
        r = {"id": it["id"], "path": it["path"], "proposed": n}
        if on_progress:
            on_progress(it["id"], "named", n)
        out.append(r)
    return {"results": out, "cost": 0.0}
