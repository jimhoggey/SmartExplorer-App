# Smart Explorer

Renames files by what is in them, using a vision model via OpenRouter. Built for ProPresenter media (a Canva export of `1.png … 24.png` becomes `Giving - Love Offering.png`, `Sermon - Anchored Wk 3 - Hebrews 6.19.png`), and just as happy naming photos, screenshots and PDFs on disk. You review and edit every name before anything is renamed, and there is an Undo.

Reads images (`png jpg webp gif bmp tiff`), iPhone photos (`heic`), PDFs (first page plus its text) and videos (`mp4 mov m4v`, three frames).

## Install

Download the latest version from the [releases page](../../releases/latest).

**Mac** (macOS 13 Ventura or later)

1. Download the `.dmg` for your Mac: `mac-apple-silicon` for Macs with an M1 or later chip, `mac-intel` for older Intel Macs (Apple menu → *About This Mac* shows which).
2. Open it and drag **Smart Explorer** onto **Applications**.
3. The first time you open it, macOS will say it can't verify the app, because it isn't signed with a paid Apple developer certificate. Click *Done*, then open *System Settings → Privacy & Security*, scroll down and click **Open Anyway** next to Smart Explorer. Or, in Terminal: `xattr -dr com.apple.quarantine "/Applications/Smart Explorer.app"`. You only do this once: updates installed from inside the app open without it.

**Windows** (10 or 11)

1. Download `SmartExplorer-…-windows-setup.exe` and run it. It installs for your user account, so no administrator password is needed.
2. If Windows shows "Windows protected your PC", click *More info → Run anyway* (the installer isn't signed with a paid certificate).
3. Start Smart Explorer from the Start menu.

## Updates

When Smart Explorer opens, it checks GitHub for a newer release. If there is one, a bar at the top offers **Update now**: the app downloads the installer for your computer, checks it matches the release (size and SHA-256), installs it and reopens. On a Mac the app must be in Applications; on Windows an install for all users asks for an administrator. *Settings → Check for updates* checks again. Run from source, the bar just links to the release (update with `git pull`). Versions before 0.4.0 can't update themselves, so install 0.4.0 by hand once.

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

1. **Load files:** drop files or a folder onto the window, click **Choose folder**, or paste a path. Choose **ProPresenter** (slides and media for ProPresenter) or **Photos & files** (everyday files, date first) and optionally type context for this batch ("Sun 12 Oct · Anchored series wk 3 · Ps Dave"). **Keep order** puts `01 `, `02 `… in front of the names so a deck stays in sequence; it turns itself on when the files are numbered in sequence (`1.png`, `2.png`… or `Slide1`, `Slide2`…) and can be ticked or unticked at any time, even after naming.
2. **Name with AI:** suggests a name for every file and shows what the batch cost on OpenRouter. Nothing on disk changes yet.
3. **Check, then rename:** click any name to change it (Escape undoes an edit), then **Rename N files**. **Undo** puts the old names back and keeps the suggestions, so one wrong name doesn't mean naming the batch again. After renaming, **Rename more files** empties the list, the context and Keep order for the next set (files on disk are not touched); before that, the same button is **Clear**.

Settings shows what naming has cost this month and in all; *Test key* shows what has been spent on the key as a whole.

The full naming convention, with examples, is in [docs/naming-convention.md](docs/naming-convention.md). To change it for good (say, Offering instead of Giving), open *Settings → Naming prompts → View and edit*. Each style has three parts you can read and change: how to name the files, the categories, and what to look for in each file. *Show full prompt* shows exactly what the AI is sent. Edits are saved on this computer, in `~/.smart-explorer/config.json`, and *Reset to default* puts the original back. The defaults live in `conventions.py`.

Names are sanitised for Windows, capped at 100 characters, and get ` (2)`, ` (3)` on collisions. Existing files are never overwritten. Undo journals live in `~/.smart-explorer/journal/`.

## Background renaming (watch a folder)

Smart Explorer can rename new files in one folder by itself, with no window open: made for a Google Drive folder that ProPresenter's playlist watches. Set it up in *Settings → Watch a folder*: the folder, the naming style and a monthly AI limit for background naming (default US$5). Turned on there, it starts watching straight away and keeps running after you close the window.

Tick **Start by itself when the computer starts** and click **Save**: Smart Explorer adds itself to the computer's start-up items, reads the entry back, and only then shows "✓ Smart Explorer is in this computer's start-up items". You don't add it yourself. **Show** opens where it is listed: the Startup folder on Windows (`Smart Explorer (background)`), *System Settings → General → Login Items → Allow in the Background* on a Mac. Only with start-up ticked does **Wait after the computer starts** apply (default 3 minutes): time for Google Drive to download the week's files before anything is renamed.

When the watched folder is in Google Drive (its path has `My Drive`, `Shared drives` or `Google Drive` in it), Smart Explorer also checks every 30 seconds that Google Drive for desktop is running (`GoogleDriveFS.exe` on Windows, "Google Drive" on a Mac). If it isn't, a notification says so once and the status bar turns red; renaming carries on, and the warning clears by itself when Drive starts. It can tell whether Drive runs, not how far its sync has got.

It works while the computer is awake: a sleeping computer renames nothing until it wakes, so set the ProPresenter computer not to sleep while it is in use.

- Files already in the folder when you turn it on are left as they are. After that, a file is new when Smart Explorer knows neither its name nor its size and modified time: a file you rename by hand, or an updated slide uploaded under the same name, is not renamed again.
- It waits for each download to finish and for a quiet minute, names files that arrive together as one batch (with Keep order numbering when they are numbered in sequence), and never renames with a guess: if naming fails, files keep their names and are tried again, at most twice per start-up, so a problem cannot keep spending.
- Before each batch it checks the key and credit with OpenRouter, which costs nothing. A rejected key or no credit pauses it until fixed.
- Notifications say when it starts, what it renamed and any problem. The window shows a status bar while watching is on. The log is `~/.smart-explorer/watch/watch.log` (*Settings → Open log*).
- From source, `.venv/bin/python desktop.py --watch` runs it in the terminal.

For the people at the ProPresenter computer: [docs/background-renaming.md](docs/background-renaming.md).

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
