# Smart Explorer

Renames files by what is in them, using a vision model via OpenRouter. Built for ProPresenter media (a Canva export of `1.png … 24.png` becomes `Giving - Love Offering.png`, `Sermon - Anchored Wk 3 - Hebrews 6.19.png`), and just as happy naming photos, screenshots and PDFs on disk. You review and edit every name before anything is renamed, and there is an Undo.

Reads images (`png jpg webp gif bmp tiff`), iPhone photos (`heic`), PDFs (first page plus its text) and videos (`mp4 mov m4v`, three frames).

## Install

Download the latest version from the [releases page](../../releases/latest).

**Mac** (macOS 13 Ventura or later)

1. Download the `.dmg` for your Mac: `mac-apple-silicon` for Macs with an M1 or later chip, `mac-intel` for older Intel Macs (Apple menu → *About This Mac* shows which).
2. Open it and drag **Smart Explorer** onto **Applications**.
3. The first time you open it, macOS will say it can't verify the app, because it isn't signed with a paid Apple developer certificate. Click *Done*, then open *System Settings → Privacy & Security*, scroll down and click **Open Anyway** next to Smart Explorer. You only do this once.

**Windows** (10 or 11)

1. Download `SmartExplorer-…-windows-setup.exe` and run it. It installs for your user account, so no administrator password is needed.
2. If Windows shows "Windows protected your PC", click *More info → Run anyway* (the installer isn't signed with a paid certificate).
3. Start Smart Explorer from the Start menu.

## Get an OpenRouter key

1. Sign up at [openrouter.ai](https://openrouter.ai) and add a few dollars of credit.
2. Create a key under *Keys*.
3. In Smart Explorer click **Settings**, paste the key, *Test key*, *Save*.

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

The three steps are shown above the files, and the coloured button is always the next one.

1. **Load files:** drop files or a folder onto the window, click **Choose folder**, or paste a path. Choose **ProPresenter** or **General** naming, optionally type context for this batch ("Sun 12 Oct · Anchored series wk 3 · Ps Dave"), and tick **Keep order** when the files are a deck that must stay in sequence (names get `01 `, `02 `… in the original order).
2. **Name with AI:** suggests a name for every file and shows what the batch cost on OpenRouter. Nothing on disk changes yet.
3. **Check, then rename:** click any name to change it, then **Rename N files**. **Undo** puts the old names back. **Clear** empties the list for the next set (files on disk are not touched).

*Settings → Test key* shows how much has been spent on your OpenRouter key so far.

The full naming convention, with examples, is in [docs/naming-convention.md](docs/naming-convention.md); to change it for good (say, Offering instead of Giving), edit `conventions.py`.

Names are sanitised for Windows, capped at 100 characters, and get ` (2)`, ` (3)` on collisions. Existing files are never overwritten. Undo journals live in `~/.smart-explorer/journal/`.

## How it keeps cost down

OpenRouter charges per token, not per request, so running requests in parallel costs nothing extra and is simply faster. The app sends each image at full resolution but groups 8 files per request, so the instructions are paid for once per 8 files, and asks for short descriptions because output tokens cost several times more than input. A second, text-only request names the whole batch together, which is what keeps similar files consistent and distinct. Packing several slides into one grid image would save a little more, but only by shrinking each slide, which loses the small text (bank details, dates, links) that tells near-duplicates apart.

## Run from source

Requires Python 3.9+.

- Mac/Linux: `./run.sh`
- Windows: double-click `run.bat`

Both create `.venv`, install `requirements.txt`, and start `desktop.py`. The first run downloads about 40 MB of libraries and takes a few minutes; after that `run.sh` starts straight away, and reinstalls only when `requirements.txt` changes. Apple's built-in Python 3.9 works: `run.sh` updates its old pip and uses ready-made packages, so nothing needs compiling. `SMART_EXPLORER_HEADLESS=1 python desktop.py` prints a URL to open in a browser instead of a window (drag and drop needs the window); `SMART_EXPLORER_MOCK=1` names files without a key, for testing.

Tests: `python -m pytest -q`. Build locally: `pip install pyinstaller && pyinstaller smart_explorer.spec` → `dist/Smart Explorer/` (and `dist/Smart Explorer.app` on a Mac).

## Releasing a new version

1. Set the new number in `version.py` (e.g. `0.2.1`) and merge it to `main`.
2. Tag that commit and push the tag: `git tag v0.2.1 && git push origin v0.2.1`.
3. GitHub Actions builds the Apple Silicon and Intel `.dmg` files and the Windows installer, checks each one (the app starts and reads PNG, HEIC and PDF; the Windows installer installs, starts and uninstalls), and publishes them as a release, in about five minutes. Point people at [releases/latest](../../releases/latest).

The tag must match `version.py` or nothing is published. *Actions → build → Run workflow* builds the same files without publishing, for testing; download them from the run's *Artifacts*.
