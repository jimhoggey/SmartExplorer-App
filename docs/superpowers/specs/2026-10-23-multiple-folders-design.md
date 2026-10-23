# Smart Explorer — Background renaming: several folders

Builds on `2026-10-08-background-renaming-design.md`, which stays the reference for
how one folder is watched. Everything there still applies to each folder.

## Goal
Background renaming watches **several folders** at once, on the Windows ProPresenter
PC first. A couple of Google Drive folders get new screens and slides; each feeds
ProPresenter through its own smart playlist. New files in any of them are renamed
by themselves.

## Decisions (agreed in brainstorming, 23 Oct 2026)
| Question | Decision |
|---|---|
| Naming style | **One style for all folders** (the existing setting). |
| Shape | **One background copy watches every folder** (approach A). Not one copy per folder, not one batch across folders. |
| Shared across folders | Naming style, monthly AI limit, start by itself, wait after start-up, the free key check, the Google Drive check, the log, the lock. |
| Per folder | Its new files, quiet minute, batches, retries, paid descriptions, known list, missing/unreadable timing, forgotten names. |
| Subfolders | Still not watched. |
| Existing setups | A saved single `folder` becomes a one-item list by itself. |

## Settings ("Watch folders")
- The section is titled **Watch folders**. The checkbox reads "Rename new files in
  these folders by itself, with no window open".
- A **list of folders**, one row each: the path and a **Remove** button. Under it,
  **Add folder**: a path box with **Choose**; a folder is added with **Add** (or Enter,
  or straight after Choose). At most **10** folders. A folder already in the list is
  not added twice (same folder whatever the case or trailing slash).
- Unchanged and shared: naming style, monthly AI limit, start by itself, wait after
  the computer starts, status line, Open log.
- **Save** with watching on and no folder: the add box turns red, "Add a folder to
  watch first. Nothing was saved yet."
- A folder that can't be found or opened at Save: its row turns red, the message
  names it ("Can't find Youth Media. … Nothing was saved yet."), nothing is saved.
- Turning watching on, or adding folders, records the files already in each **newly
  added** folder (left as they are). The confirm names each new folder and its count:
  "Smart Explorer will rename new files in these folders by itself, even with this
  window closed. Sunday Media: 34 files already in it will be left as they are.
  Youth Media: it's empty."
- Removing a folder stops watching it at once; its known record is kept (adding it
  back later leaves what is there alone, as turning on does).

## Saved data
`config.json` → `watch.folders`: a list of absolute path strings (deduplicated,
at most 10). `config.watch_settings()` returns `folders` and no longer `folder`;
an old config with only `folder` gives `folders: [folder]`. Saving writes `folders`
and drops `folder`. `known.json` is already per folder: unchanged.

## Watching
- One `Watcher` coordinates; each folder has a `FolderWatch` holding what today's
  watcher keeps for its folder: `seen`, `activity`, `descs`, `failures`, `given_up`,
  `handled`, `absent`, `unavailable_since`, `batches`.
- Every 5 s the watcher reads the settings, adds a `FolderWatch` for a new folder
  and drops one for a removed folder, then looks at each folder in list order and
  runs any batch that is due, folder by folder. A batch only ever holds one
  folder's files: names fit that folder's existing names (`scanner.siblings`), and
  Keep order numbers that folder's set.
- The start-up wait, the free key check before each batch, the monthly limit, the
  no-key check and the Google Drive check are shared, as today.
- A missing or unreadable folder pauses **that folder only**, with today's grace
  (start-up wait plus 2 minutes, and 2 minutes in a row); the others carry on.
- A folder with no known record is recorded first (the fail-safe), per folder.

## What people see
Single-folder setups keep today's exact texts. With more than one folder:
| When | Text |
|---|---|
| Watcher starts | Smart Explorer is watching Sunday Media and Youth Media. New files will be renamed in 3 minutes. (3 or more: "watching 3 folders") |
| Wait over, nothing new anywhere | Checked Sunday Media and Youth Media: no new files. (3 or more: "Checked 3 folders: …") |
| Batch starts | Renaming 3 new files in Youth Media… |
| Batch done | 3 files renamed and ready for ProPresenter in Youth Media: A, B, C. |
| Batch done with failures | 2 files renamed and ready for ProPresenter in Youth Media. 1 couldn't be named yet: 7.png |
| File given up | Couldn't name 7.png. It's still in Youth Media under its old name. (unchanged) |
| Folder not found / can't open | unchanged: they already name the folder |
| Google Drive not running | names the Drive folders: "…can't arrive in Sunday Media and Youth Media." |

Status bar with more than one folder:
- Watching 2 folders · last batch 8:04am, 12 files in Youth Media
- Found 1 new file in Youth Media. Renaming in 45 s, in case more are on the way.
- Waiting for 1 file to finish downloading in Youth Media
- Renaming 3 files in Youth Media…
- Watching 2 folders · can't find Youth Media (state `warning`, red bar)
- Shared problems as today ("Paused: out of OpenRouter credit", "Waiting for Google Drive, 2 min left").

## Window API
- `GET /api/watch` → `settings.folders`.
- `POST /api/watch/preview {"folders": [...]}` → `{"counts": {path: n}}`; a folder that
  can't be found or opened → 400 `{"error", "folder": path}`.
- `POST /api/watch {"folders": [...], …}` validates every folder (absolute, exists,
  can be listed), records newly added ones, saves, then starts or stops background
  renaming as today. Errors name the folder and return it as `folder`.
- `/api/rename`: renames made in the window inside **any** watched folder are added
  to that folder's known list.

## Windows proof and tests
- Unit tests: settings migration and dedupe; two folders batched separately; a
  missing folder doesn't stop the other; files already in an added folder are left
  alone; removing a folder stops it; texts for one folder unchanged and for two.
- `scripts/smoke_watch.py` and `scripts/smoke_windows_startup.py` watch **two
  folders**, drop files in both, and expect both renamed: from source, on the built
  Mac app, and on the built Windows app in CI (including after starting from the
  Windows Startup shortcut).

## Build order
1. `config.watch_settings()` with `folders` and the migration.
2. `watch.py`: `FolderWatch` per folder, `Watcher` coordinating; multi-folder texts.
3. `app.py` endpoints and window renames for every watched folder.
4. Settings UI: folder list, add, remove, per-folder errors, multi-folder confirm.
5. Smoke scripts for two folders; README, volunteer page, spec references.
6. Version 0.7.0, PR (Auto-fix on), CI green on Windows, merge, tag, release.
