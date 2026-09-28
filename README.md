# Smart Explorer

Renames files by what is in them, using a vision model via OpenRouter. Built for ProPresenter media (a Canva export of `1.png … 24.png` becomes `Giving - Love Offering.png`, `Sermon - Anchored Wk 3 - Hebrews 6.19.png`), and just as happy naming photos, screenshots and PDFs on disk. You review and edit every name before anything is renamed, and there is an Undo.

Reads images (`png jpg webp gif bmp tiff`), iPhone photos (`heic`), PDFs (first page plus its text) and videos (`mp4 mov m4v`, three frames).

## Install

**Windows:** download `SmartExplorer-Windows.zip` from the latest [release](../../releases), unzip anywhere, run `SmartExplorer\SmartExplorer.exe`. If SmartScreen warns, click *More info → Run anyway*.

**Mac:** download `SmartExplorer-macOS.zip`, unzip, drag **SmartExplorer.app** to Applications. The app is ad-hoc signed, not notarised, so macOS quarantines it on first download. Clear that once in Terminal, then open it normally:

```
xattr -dr com.apple.quarantine /Applications/SmartExplorer.app
```

## Get an OpenRouter key

1. Sign up at [openrouter.ai](https://openrouter.ai) and add a few dollars of credit.
2. Create a key under *Keys*.
3. In Smart Explorer click the gear, paste the key, *Test key*, *Save*.

The key is stored in `~/.smart-explorer/config.json`. Nothing is sent anywhere except OpenRouter.

## Choosing a model

| Model | Per file (rough) | Pick it when |
|---|---|---|
| **Claude Sonnet 5** (default) | ~0.5c | You want names you rarely need to fix. Best text reading of the three. |
| Gemini 3.8 Flash | ~0.2c | Big batches where speed matters. Price doubles on 1 Jan 2027. |
| Gemini 3.1 Flash Lite | <0.1c | Very large batches of simple files. |

Any other OpenRouter model that accepts images can be entered under *Custom…*. The app shows what each batch actually cost when it finishes.

To choose on evidence rather than benchmarks, run the same folder through several models and compare the names side by side in a report that opens in your browser. Nothing is renamed, and it asks before spending. From the project folder, after `./run.sh` has set up `.venv` (on Windows use `.venv\Scripts\python`):

```
.venv/bin/python scripts/compare_models.py ~/Desktop/Sunday-Slides
.venv/bin/python scripts/compare_models.py ~/Pictures/Camp --profile general --context "Youth camp, Sep 2026"
```

## Use

1. **Drop** files or a folder onto the window, **Pick folder**, or paste a path.
2. Choose **ProPresenter** or **General** naming, and optionally type context for this batch ("Sun 12 Oct · Anchored series wk 3 · Ps Dave").
3. Tick **Keep order** when the files are a deck that must stay in sequence: names get `01 `, `02 `… in the original order.
4. **Name with AI**, edit any name inline, then **Rename all**. **Undo** reverts the last batch.

The full naming convention, with examples, is in [docs/naming-convention.md](docs/naming-convention.md); to change it for good (say, Offering instead of Giving), edit `conventions.py`.

Names are sanitised for Windows, capped at 100 characters, and get ` (2)`, ` (3)` on collisions. Existing files are never overwritten. Undo journals live in `~/.smart-explorer/journal/`.

## How it keeps cost down

OpenRouter charges per token, not per request, so running requests in parallel costs nothing extra and is simply faster. The app sends each image at full resolution but groups 8 files per request, so the instructions are paid for once per 8 files, and asks for short descriptions because output tokens cost several times more than input. A second, text-only request names the whole batch together, which is what keeps similar files consistent and distinct. Packing several slides into one grid image would save a little more, but only by shrinking each slide, which loses the small text (bank details, dates, links) that tells near-duplicates apart.

## Run from source

Requires Python 3.9+.

- Mac/Linux: `./run.sh`
- Windows: double-click `run.bat`

Both create `.venv`, install `requirements.txt`, and start `desktop.py`. The first run downloads about 40 MB of libraries and takes a few minutes; after that `run.sh` starts straight away, and reinstalls only when `requirements.txt` changes. Apple's built-in Python 3.9 works: `run.sh` updates its old pip and uses ready-made packages, so nothing needs compiling. `SMART_EXPLORER_HEADLESS=1 python desktop.py` prints a URL to open in a browser instead of a window (drag and drop needs the window); `SMART_EXPLORER_MOCK=1` names files without a key, for testing.

Tests: `python -m pytest -q`. Build: `pip install pyinstaller && pyinstaller smart_explorer.spec` → `dist/SmartExplorer/`. Pushing a `v*` tag builds Windows and Mac zips via GitHub Actions and checks the packaged app can read PNG, HEIC and PDF.
