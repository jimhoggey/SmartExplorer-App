import io
import json
from urllib.error import HTTPError, URLError

import pytest

import conventions
import namer


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(namer.time, "sleep", lambda s: None)


def stub(monkeypatch, content, seen=None, cost=0.0012):
    body = json.dumps({"choices": [{"message": {"content": content}}], "usage": {"cost": cost}}).encode()

    def fake(req, timeout=None):
        if seen is not None:
            seen.append(req)
        return io.BytesIO(body)

    monkeypatch.setattr(namer, "urlopen", fake)


def raise_(exc):
    def fake(req, timeout=None):
        raise exc

    return fake


ITEM = {"id": 1, "name": "4.png", "path": "/x/Sunday Slides/4.png", "kind": "image"}
ENC = {"images": ["abc"], "text": "", "facts": {"size": "1920x1080", "aspect": "16:9 landscape"}}
DESC = {"category": "Giving", "subject": "Giving", "text": "Give", "visual": "black", "date": "", "notes": ""}
READ = json.dumps({"files": [dict(DESC, n=1)]})


def files_in(content):
    return sum(c["type"] == "text" and c["text"].startswith("File ") for c in content)


def test_parse_json_fenced_and_prefixed():
    assert namer.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert namer.parse_json('Sure! ["x", "y"] done') == ["x", "y"]
    assert namer.parse_json('Names {see below}: ["A", "B"]') == ["A", "B"]
    with pytest.raises(namer.NamerError):
        namer.parse_json("no json here")


def test_chat_http_error(monkeypatch):
    err = HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))
    monkeypatch.setattr(namer, "urlopen", raise_(err))
    with pytest.raises(namer.NamerError, match="401"):
        namer.chat("k", "m", [])


def test_chat_unknown_model_says_what_to_do(monkeypatch):
    err = HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error":{"message":"No endpoints found for model x"}}'))
    monkeypatch.setattr(namer, "urlopen", raise_(err))
    with pytest.raises(namer.NamerError, match="pick another model in Settings"):
        namer.chat("k", "m", [])


def test_chat_sends_schema_effort_and_returns_cost(monkeypatch):
    seen = []
    stub(monkeypatch, '{"a": 1}', seen, cost=0.0042)
    text, cost = namer.chat("k", "m", [{"role": "user", "content": "hi"}], schema={"type": "object"}, effort="low", max_tokens=99)
    body = json.loads(seen[0].data)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert body["reasoning"] == {"effort": "low"} and body["max_tokens"] == 99
    assert (text, cost) == ('{"a": 1}', 0.0042)


def test_chat_empty_reply_is_an_error(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": None}, "finish_reason": "length"}]}).encode()
    monkeypatch.setattr(namer, "urlopen", lambda req, timeout=None: io.BytesIO(body))
    with pytest.raises(namer.NamerError, match="length"):
        namer.chat("k", "m", [])


def test_prompts_carry_convention_and_context():
    r = namer.read_prompt("propresenter", context="Sun 12 Oct")
    p = conventions.get("propresenter")
    assert p["reader"] in r and p["categories"] in r
    assert p["rules"] not in r  # the style rules are the namer's job; the reader stays lean
    assert p["rules"] in namer.name_prompt("propresenter")
    assert "Context for this batch from the user:\nSun 12 Oct" in r
    n = namer.name_prompt("general")
    assert conventions.get("general")["rules"] in n and "Context for" not in n and "house rules" not in n.lower()


def test_closing_slides_have_their_own_category():
    """A thanks-for-coming screen was named Welcome - Thanks For Coming, because
    Welcome also covered holding slides."""
    cats = conventions.get("propresenter")["categories"]
    assert "Closing (end of service: thanks for coming" in cats and "holding" not in cats
    assert namer.name_prompt("nonsense") == namer.name_prompt(conventions.DEFAULT_PROFILE)


def test_describe(monkeypatch):
    seen = []
    stub(monkeypatch, READ, seen)
    d, cost = namer.describe("k", "m", ITEM, ENC, "propresenter", context="Anchored wk 3")
    assert d["category"] == "Giving" and "n" not in d and cost == 0.0012
    assert d["facts"] == {"file": "4.png", "folder": "Sunday Slides", "kind": "image", "size": "1920x1080", "aspect": "16:9 landscape"}
    assert seen[0].get_header("Authorization") == "Bearer k"
    body = json.loads(seen[0].data)
    label, image = body["messages"][1]["content"][:2]
    assert label["text"].startswith("File 1 of 1. Facts: ") and '"folder": "Sunday Slides"' in label["text"]
    assert image["image_url"]["url"] == "data:image/jpeg;base64,abc"
    assert "Anchored wk 3" in body["messages"][0]["content"]
    assert body["reasoning"] == {"effort": namer.READ_EFFORT}


def test_read_batch_labels_each_file_and_matches_by_number(monkeypatch):
    seen = []
    reply = {"files": [dict(DESC, n=2, subject="Second"), dict(DESC, n=1, subject="First")]}
    stub(monkeypatch, json.dumps(reply), seen)
    items = [dict(ITEM, name="a.png"), dict(ITEM, name="b.png")]
    descs, cost = namer.read_batch("k", "m", items, [ENC, dict(ENC, images=["def"])])
    assert [d["subject"] for d in descs] == ["First", "Second"]
    assert [d["facts"]["file"] for d in descs] == ["a.png", "b.png"]
    content = json.loads(seen[0].data)["messages"][1]["content"]
    assert [c["type"] for c in content] == ["text", "image_url", "text", "image_url", "text"]
    assert content[2]["text"].startswith("File 2 of 2.") and content[3]["image_url"]["url"].endswith("def")


def test_read_batch_short_reply_is_an_error_that_keeps_its_cost(monkeypatch):
    stub(monkeypatch, READ, cost=0.02)  # describes 1 of 2
    with pytest.raises(namer.NamerError, match="described 1 of 2") as e:
        namer.read_batch("k", "m", [ITEM, ITEM], [ENC, ENC])
    assert e.value.cost == 0.02


def test_describe_sends_pdf_text_and_video_hint(monkeypatch):
    seen = []
    stub(monkeypatch, READ, seen)
    namer.describe("k", "m", dict(ITEM, kind="pdf"), dict(ENC, text="TAX INVOICE 4471"))
    namer.describe("k", "m", dict(ITEM, kind="video"), dict(ENC, images=["a", "b", "c"]))
    pdf, video = (json.loads(r.data)["messages"][1]["content"] for r in seen)
    assert any("TAX INVOICE 4471" in c.get("text", "") for c in pdf)
    assert sum(c["type"] == "image_url" for c in video) == 3
    assert any("frames" in c.get("text", "") for c in video)


def test_describe_error(monkeypatch):
    monkeypatch.setattr(namer, "urlopen", raise_(URLError("down")))
    d, cost = namer.describe("k", "m", ITEM, ENC)
    assert "error" in d and "down" in d["error"] and cost == 0


DESCS = [
    {"i": 0, "original": "a.png", "subject": "Giving"},
    {"i": 1, "original": "b.png", "subject": "Giving"},
    {"i": 2, "original": "c.png", "subject": ""},
]


def test_name_all(monkeypatch):
    stub(monkeypatch, '{"names": [{"i": 0, "name": "A"}, {"i": 1, "name": "B"}, {"i": 2, "name": "C"}]}', cost=0.01)
    assert namer.name_all("k", "m", DESCS) == (["A", "B", "C"], None, 0.01)


def test_name_all_matches_by_index_not_position(monkeypatch):
    stub(monkeypatch, '{"names": [{"i": 2, "name": "C"}, {"i": 0, "name": "A"}, {"i": 1, "name": "B"}]}')
    assert namer.name_all("k", "m", DESCS)[0] == ["A", "B", "C"]


def test_name_all_tolerates_wrapped_shapes(monkeypatch):
    stub(monkeypatch, '{"names": [{"index": 0, "name": "A"}, "B", "C"]}')
    assert namer.name_all("k", "m", DESCS)[0] == ["A", "B", "C"]
    stub(monkeypatch, '["A", "B", "C"]')
    assert namer.name_all("k", "m", DESCS)[0] == ["A", "B", "C"]


def test_name_all_cleans_and_dedupes(monkeypatch):
    stub(monkeypatch, '["Scripture - John 3:16.png", "\\"Giving / Title\\"", "Giving - Title"]')
    assert namer.name_all("k", "m", DESCS)[0] == ["Scripture - John 3.16", "Giving - Title", "Giving - Title (2)"]


def test_name_all_reports_failure_it_falls_back_from(monkeypatch):
    """A failed naming call must never look like success: the fallback is raw
    file text, which is plausible enough to be renamed by reflex."""
    monkeypatch.setattr(namer, "urlopen", raise_(URLError("down")))
    names, err, cost = namer.name_all("k", "m", DESCS)
    assert names == ["Giving", "Giving (2)", "c"]
    assert err and "AI naming failed" in err

    stub(monkeypatch, '["A", "B"]')  # wrong length
    names, err, _ = namer.name_all("k", "m", DESCS)
    assert names == ["Giving", "Giving (2)", "c"] and err


def test_name_all_chunks_big_batches_and_passes_used_names(monkeypatch):
    calls = []

    def chat(key, model, messages, **kw):
        payload = json.loads(messages[1]["content"])
        calls.append(payload)
        return json.dumps({"names": [{"i": f["i"], "name": "N%d" % f["i"]} for f in payload["files"]]}), 0.5

    monkeypatch.setattr(namer, "chat", chat)
    monkeypatch.setattr(namer, "CHUNK", 2)
    descs = [{"i": i, "original": "%d.png" % i} for i in range(5)]
    names, err, cost = namer.name_all("k", "m", descs)
    assert names == ["N0", "N1", "N2", "N3", "N4"] and err is None and cost == 1.5
    assert [len(c["files"]) for c in calls] == [2, 2, 1]
    assert "already_used" not in calls[0] and calls[2]["already_used"] == ["N0", "N1", "N2", "N3"]


def test_clean():
    assert namer.clean("Sermon - Anchored Wk 3 - Title.png", "7.png") == "Sermon - Anchored Wk 3 - Title"
    assert namer.clean("Service 10:30am / Hall", "a.jpg") == "Service 10.30am - Hall"
    assert namer.clean("24/7 Prayer", "a.jpg") == "24-7 Prayer"
    assert namer.clean("  'Giving  -   Title'  ") == "Giving - Title"
    assert namer.clean("Giving - ") == "Giving"


def fake_chat(fail_naming=False, calls=None):
    def chat(key, model, messages, **kw):
        content = messages[1]["content"]
        if isinstance(content, list):
            if calls is not None:
                calls.append(files_in(content))
            return json.dumps({"files": [dict(DESC, n=n) for n in range(1, files_in(content) + 1)]}), 0.001
        if fail_naming:
            raise namer.NamerError("HTTP 429")
        files = json.loads(content)["files"]
        return json.dumps({"names": [{"i": f["i"], "name": "Name %d" % f["i"]} for f in files]}), 0.01

    return chat


ITEMS = [{"id": i, "path": "/x/%d.png" % i, "name": "%d.png" % i, "kind": "image"} for i in range(3)]


def test_run_marks_every_item_when_naming_failed(monkeypatch):
    monkeypatch.setattr(namer, "chat", fake_chat(fail_naming=True))
    out = namer.run("k", "m", ITEMS[:2], lambda i: ENC)
    assert all("429" in r["error"] for r in out["results"])


def test_request_retries_on_429_then_succeeds(monkeypatch):
    calls = []

    def flaky(req, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise HTTPError("https://x/y", 429, "rate limited", {}, io.BytesIO(b"slow down"))
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(namer, "urlopen", flaky)
    assert namer._request("https://x/y", "k") == {"ok": True}
    assert len(calls) == 3


def test_run_reads_in_batches(monkeypatch):
    calls = []
    monkeypatch.setattr(namer, "chat", fake_chat(calls=calls))
    items = [{"id": i, "path": "/x/%d.png" % i, "name": "%d.png" % i, "kind": "image"} for i in range(19)]
    out = namer.run("k", "m", items, lambda i: ENC)
    assert sorted(calls) == [3, 8, 8]  # 19 files in three vision requests, not nineteen
    assert [r["proposed"] for r in out["results"]] == ["Name %d" % i for i in range(19)]


def test_run_falls_back_to_one_file_per_request(monkeypatch):
    calls = []
    good = fake_chat()

    def chat(key, model, messages, **kw):
        content = messages[1]["content"]
        if isinstance(content, list):
            calls.append(files_in(content))
        if isinstance(content, list) and files_in(content) > 1:
            raise namer.NamerError("Model described 2 of 3 files", cost=0.005)
        if isinstance(content, list) and any("bad.png" in c.get("text", "") for c in content):
            raise namer.NamerError("HTTP 400: image could not be processed")
        return good(key, model, messages, **kw)

    monkeypatch.setattr(namer, "chat", chat)
    items = [{"id": i, "path": "/x/%s" % n, "name": n, "kind": "image"} for i, n in enumerate(["a.png", "bad.png", "c.png"])]
    out = namer.run("k", "m", items, lambda i: ENC)
    assert calls == [3, 1, 1, 1]
    assert [r["proposed"] for r in out["results"]] == ["Name 0", "bad", "Name 2"]
    assert "400" in out["results"][1]["error"] and "error" not in out["results"][0]
    assert out["cost"] == pytest.approx(0.005 + 0.002 + 0.01)


def test_run_does_not_retry_file_by_file_on_a_bad_key(monkeypatch):
    calls = []

    def chat(key, model, messages, **kw):
        calls.append(1)
        raise namer.NamerError("OpenRouter returned HTTP 401: bad key", status=401)

    monkeypatch.setattr(namer, "chat", chat)
    out = namer.run("k", "m", ITEMS, lambda i: ENC)
    assert len(calls) == 1 and all("401" in r["error"] for r in out["results"])


def test_run(monkeypatch):
    monkeypatch.setattr(namer, "chat", fake_chat())

    def encode(item):
        if item["id"] == 1:
            raise OSError("bad file")
        return ENC

    calls = []
    out = namer.run("k", "m", ITEMS, encode, on_progress=lambda *a: calls.append(a))
    assert [r["proposed"] for r in out["results"]] == ["Name 0", "1", "Name 2"]
    assert "error" in out["results"][1] and "error" not in out["results"][0]
    assert {c[0] for c in calls if c[1] == "named"} == {0, 1, 2}
    assert out["cost"] == pytest.approx(0.011)  # one vision request for the two readable files, one naming request


def test_run_passes_facts_to_naming(monkeypatch):
    seen = []
    chat = fake_chat()

    def spy(key, model, messages, **kw):
        if not isinstance(messages[1]["content"], list):
            seen.append(json.loads(messages[1]["content"]))
        return chat(key, model, messages, **kw)

    monkeypatch.setattr(namer, "chat", spy)
    namer.run("k", "m", ITEMS[:1], lambda i: dict(ENC, facts={"duration": "300s"}))
    f = seen[0]["files"][0]
    assert f["facts"]["duration"] == "300s" and f["original"] == "0.png" and f["category"] == "Giving"


def test_mock_run():
    items = [{"id": 7, "path": "/x/a.png", "name": "a.png"}, {"id": 8, "path": "/x/b.png", "name": "b.png"}]
    calls = []
    out = namer.mock_run(items, on_progress=lambda *a: calls.append(a))
    assert out == {"results": [{"id": 7, "path": "/x/a.png", "proposed": "Slide 1"},
                               {"id": 8, "path": "/x/b.png", "proposed": "Slide 2"}], "cost": 0.0}
    assert len(calls) == 2


def test_saved_prompt_edits_go_on_top_of_the_defaults():
    import config
    config.save(prompt_edits={"propresenter": {"rules": "Name it from {categories} please", "reader": "   ", "bogus": "x"}})
    base = conventions.PROFILES["propresenter"]
    p = conventions.get("propresenter")
    assert p["rules"] == "Name it from %s please" % base["categories"]
    assert p["reader"] == base["reader"] and "bogus" not in p  # a blank edit means the default
    n = namer.name_prompt("propresenter")
    assert "Name it from" in n and "Reply with JSON only" in n  # the reply format is not editable
    assert conventions.get("general")["rules"] == conventions.PROFILES["general"]["rules"].replace(
        "{categories}", conventions.PROFILES["general"]["categories"])


def test_a_draft_previews_without_saving():
    r = namer.read_prompt("general", draft={"categories": "Alpha · Beta", "reader": "Look hard."})
    assert "Alpha · Beta" in r and "Look hard." in r and '{"files"' in r
    assert conventions.edits("general") == {}


def test_check_key(monkeypatch):
    monkeypatch.setattr(namer, "urlopen", lambda req, timeout=None: io.BytesIO(b'{"data": {"label": "sk-1"}}'))
    assert namer.check_key("k") == {"ok": True, "label": "sk-1"}
    monkeypatch.setattr(namer, "urlopen", raise_(URLError("down")))
    assert namer.check_key("k")["ok"] is False


def test_name_all_keeps_cost_when_reply_is_not_json(monkeypatch):
    stub(monkeypatch, "Sorry, I can't help with that.", cost=0.05)
    names, err, cost = namer.name_all("k", "m", DESCS)
    assert err and cost == 0.05


def test_name_all_duplicate_entry_does_not_discard_names(monkeypatch):
    stub(monkeypatch, json.dumps({"names": [{"i": 0, "name": "A"}, {"i": 0, "name": "A again"},
                                            {"i": 1, "name": "B"}, {"i": 2, "name": "C"}]}))
    assert namer.name_all("k", "m", DESCS)[:2] == (["A", "B", "C"], None)


def test_name_all_prefers_the_names_key(monkeypatch):
    stub(monkeypatch, json.dumps({"notes": ["x", "y", "z"], "names": [{"i": 0, "name": "A"}, {"i": 1, "name": "B"}, {"i": 2, "name": "C"}]}))
    assert namer.name_all("k", "m", DESCS)[0] == ["A", "B", "C"]


def test_name_all_avoids_names_already_in_the_folder(monkeypatch):
    seen = []
    stub(monkeypatch, '["Giving", "Giving - Love Offering", "Welcome"]', seen)
    names, err, _ = namer.name_all("k", "m", DESCS, existing=["Giving", "Background"])
    assert json.loads(json.loads(seen[0].data)["messages"][1]["content"])["already_used"] == ["Giving", "Background"]
    assert names == ["Giving (2)", "Giving - Love Offering", "Welcome"]  # a clash the model missed shows before renaming


def test_read_batch_rejects_extra_descriptions(monkeypatch):
    """Three entries for two files (say, a video's frames described separately)
    means the numbering can't be trusted, so the batch is retried file by file."""
    stub(monkeypatch, json.dumps({"files": [dict(DESC, n=1), dict(DESC, n=2), dict(DESC, n=3)]}))
    with pytest.raises(namer.NamerError, match="3 descriptions for 2 files"):
        namer.read_batch("k", "m", [ITEM, ITEM], [ENC, ENC])


def test_run_model_keys_cannot_override_the_apps(monkeypatch):
    seen = []

    def chat(key, model, messages, **kw):
        content = messages[1]["content"]
        if isinstance(content, list):
            return json.dumps({"files": [dict(DESC, n=n, i=99, original=["x"]) for n in range(1, files_in(content) + 1)]}), 0.0
        files = json.loads(content)["files"]
        seen.append(files)
        return json.dumps({"names": [{"i": f["i"], "name": "Name %d" % f["i"]} for f in files]}), 0.0

    monkeypatch.setattr(namer, "chat", chat)
    out = namer.run("k", "m", ITEMS, lambda i: ENC)
    assert [f["i"] for f in seen[0]] == [0, 1, 2] and seen[0][0]["original"] == "0.png"
    assert [r["proposed"] for r in out["results"]] == ["Name 0", "Name 1", "Name 2"]


def test_run_passes_existing_names_to_naming(monkeypatch):
    seen = []
    chat = fake_chat()

    def spy(key, model, messages, **kw):
        if not isinstance(messages[1]["content"], list):
            seen.append(json.loads(messages[1]["content"]))
        return chat(key, model, messages, **kw)

    monkeypatch.setattr(namer, "chat", spy)
    namer.run("k", "m", ITEMS[:1], lambda i: ENC, existing=["Giving"])
    assert seen[0]["already_used"] == ["Giving"]


def test_check_key_reports_spend_and_limit(monkeypatch):
    body = b'{"data": {"label": "sk-or-v1-abc", "usage": 1.2345, "limit_remaining": 8.5, "is_free_tier": false}}'
    monkeypatch.setattr(namer, "urlopen", lambda req, timeout=None: io.BytesIO(body))
    assert namer.check_key("k") == {"ok": True, "label": "sk-or-v1-abc", "spent": 1.2345, "left": 8.5}


def test_chat_asks_openrouter_for_cost(monkeypatch):
    seen = []
    stub(monkeypatch, "{}", seen)
    namer.chat("k", "m", [])
    assert json.loads(seen[0].data)["usage"] == {"include": True}


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


def test_a_refused_naming_request_keeps_its_http_status(monkeypatch):
    monkeypatch.setattr(namer, "urlopen", raise_(HTTPError("https://x", 402, "no", {}, io.BytesIO(b"no credit"))))
    names, err, cost = namer.name_all("k", "m", DESCS)
    assert "402" in err and err.status == 402
    out = namer.name_described("k", "m", ITEMS[:1], [dict(DESC)])
    assert out["name_status"] == 402
    monkeypatch.setattr(namer, "chat", fake_chat())
    assert namer.name_described("k", "m", ITEMS[:1], [dict(DESC)])["name_status"] is None


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
