"""Name the same files with several models and compare the results side by side.

    python scripts/compare_models.py ~/Desktop/Sunday-Slides
    python scripts/compare_models.py ~/Pictures/Camp --profile general --context "Youth camp, Sep 2026"
    python scripts/compare_models.py FOLDER --models anthropic/claude-sonnet-5,google/gemini-3.8-flash

Nothing is renamed. It makes paid OpenRouter calls (it asks first), using the key
saved in the app or OPENROUTER_API_KEY.
Writes model-comparison.html with a thumbnail and each model's name per file.
"""
import argparse
import html
import os
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import conventions  # noqa: E402
import namer  # noqa: E402
import prep  # noqa: E402
import scanner  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="folders and/or files")
    ap.add_argument("--models", default=",".join(m["id"] for m in config.MODELS), help="comma-separated OpenRouter model ids")
    ap.add_argument("--profile", default=conventions.DEFAULT_PROFILE, choices=sorted(conventions.PROFILES))
    ap.add_argument("--context", default="", help="context for the AI, as typed in the app")
    ap.add_argument("--limit", type=int, default=0, help="only the first N files (0 = all)")
    ap.add_argument("--out", default="model-comparison.html")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    a = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY") or config.load().get("key")
    if not key:
        sys.exit("No key: save one in the app's Settings, or set OPENROUTER_API_KEY.")
    items = scanner.scan(*[str(Path(p).expanduser().resolve()) for p in a.paths])
    if a.limit:
        items = items[:a.limit]
    if not items:
        sys.exit("No supported files found.")
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    print("%d files x %d models, profile %s. This makes paid OpenRouter calls." % (len(items), len(models), a.profile))
    if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
        return

    encoded = {}  # read each file once, not once per model

    def encode(item):
        if item["path"] not in encoded:
            encoded[item["path"]] = prep.encode(item)
        return encoded[item["path"]]

    runs = []
    for m in models:
        print("  %s ..." % m, end="", flush=True)
        t = time.time()
        try:
            out = namer.run(key, m, items, encode, profile=a.profile, context=a.context)
            runs.append({"model": m, "secs": time.time() - t, "cost": out["cost"], "by_path": {r["path"]: r for r in out["results"]}})
            print(" %.0fs, $%.3f" % (runs[-1]["secs"], out["cost"]))
        except Exception as e:  # keep going: one bad model id should not sink the comparison
            runs.append({"model": m, "secs": time.time() - t, "cost": 0.0, "by_path": {}, "error": str(e)})
            print(" failed: %s" % e)

    write_report(Path(a.out), items, runs, a)
    print("\nWrote %s" % Path(a.out).resolve())
    try:
        webbrowser.open(Path(a.out).resolve().as_uri())
    except Exception:
        pass


def write_report(out, items, runs, a):
    e = html.escape
    head = "".join("<th>%s<small>%.0fs · $%.3f%s</small></th>" % (
        e(r["model"]), r["secs"], r["cost"], " · " + e(r["error"]) if r.get("error") else "") for r in runs)
    rows = []
    for it in items:
        try:
            thumb = '<img src="data:image/jpeg;base64,%s">' % prep.thumb_b64(it["path"], it["kind"])
        except Exception:
            thumb = ""
        cells = []
        for r in runs:
            res = r["by_path"].get(it["path"]) or {}
            err = res.get("error")
            cells.append('<td class="%s" title="%s">%s</td>' % ("err" if err else "", e(err or ""), e(res.get("proposed", ""))))
        rows.append("<tr><td>%s<div>%s</div></td>%s</tr>" % (thumb, e(it["name"]), "".join(cells)))
    out.write_text("""<!doctype html><meta charset="utf-8"><title>Model comparison</title>
<style>
body{font:14px/1.4 -apple-system,"Segoe UI",sans-serif;margin:24px;color:#1c1d20;background:#fafafa}
table{border-collapse:collapse;width:100%%}th,td{border:1px solid #ddd;padding:8px;vertical-align:top;text-align:left;background:#fff}
th small{display:block;font-weight:400;color:#666;margin-top:3px}img{width:200px;display:block;margin-bottom:4px;background:#000}
td div{font:12px ui-monospace,Menlo,monospace;color:#666}td.err{color:#b3261e}
</style>
<h1>Model comparison</h1><p>Profile: %s · Context: %s · %d files</p>
<table><tr><th>File</th>%s</tr>%s</table>""" % (e(a.profile), e(a.context or "none"), len(items), head, "".join(rows)), "utf-8")


if __name__ == "__main__":
    main()
