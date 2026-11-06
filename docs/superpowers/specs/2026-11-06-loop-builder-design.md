# Smart Explorer: Loop Builder (folders rendered into one looping video)

Builds on `2026-10-08-background-renaming-design.md` and `2026-10-23-multiple-folders-design.md`,
which stay the reference for renaming. Source brief: Fynn's `LOOP_BUILDER.md` (mapped 22 Oct 2026,
updated 6 Nov 2026), whose verified facts about ProPresenter on the church PC are repeated here
where they matter.

## Goal
A volunteer drops, replaces or deletes a screen (a picture or a video) in the pre-service or
post-service loop folder on Google Drive. A few minutes later ProPresenter's loop plays it, with
nobody touching ProPresenter or the PC. Smart Explorer becomes ProPresenter's second brain: one
table in Settings says which folder is which, what Smart Explorer does with it, and where its video
goes.

## Why a video (verified on the church PC, 22 Oct)
- New files import with Settings → Import defaults: an image gets Duration None and Next None, so
  new images don't cycle; a video gets Loop. Changing the global defaults would change every import
  at church, so they stay as they are.
- So each loop folder is rendered into **one video**, which ProPresenter imports as Loop.

## Decisions (agreed in brainstorming, 6 Nov 2026)
| Question | Decision |
|---|---|
| Where it lives | **Inside Smart Explorer**, in the background process that already renames (approach A). Not a separate app or process, not window-only. |
| Which folders render | Only rows with **Render into video** ticked (the pre-service and post-service loops). Each row also has **Rename new files**; a folder can have one or both. |
| Output | **One video per loop, fixed name**: the row's name plus `.mp4` ("Pre-service loop.mp4"), in the row's **Save video to** folder, which ProPresenter's smart playlist watches. Runsheet Pilot finds it by that name. No dates. |
| When | Whenever a file in the source folder is added, deleted, renamed or changed: rendered again, so the video is always current. |
| Service times | Set in Settings. No render starts and no video is swapped during them; changes are rendered when they end. |
| Order | File-name order, sorted as File Explorer sorts (2 before 10). |
| Pictures | 10 s each, fitted inside 1920×1080 with black bars, never cropped. |
| Animated GIF / WebP | Plays its animation: repeated to fill 10 s if shorter, played once at full length if longer. |
| Videos | Full length, sound removed, fitted like pictures. |
| Transition | 1 s crossfade between screens, and from the last screen into the first, so the loop wraps with no jump. |
| File | MP4, H.264, 1920×1080, 30 fps, no sound track. |
| Renderer | The ffmpeg already bundled with Smart Explorer (`imageio-ffmpeg`): nothing to install on the PC. |

## Risk tested first: replacing a video under the same name
On 22 Oct a file replaced in place under the same name dropped out of the smart playlist and did
not come back (verified). A fixed name meets that case on every render. Smart Explorer gives it the
best chance (render elsewhere, then swap in one step: see The swap), and the **first build step
after the renderer is a rig test** (see Rig test). If the smart playlist still drops the video, we
stop and choose a fallback before building the rest (for example dated names, the old one deleted,
and Runsheet Pilot picking the newest).

## Settings: the Folders table
- The Settings section "Watch folders" becomes **Folders**. The dialog is wide, as Naming prompts is.
- The master checkbox reads **"Watch these folders by itself, with no window open"**. Shared and
  unchanged: naming style, monthly AI limit, start by itself, wait after the computer starts,
  status line, Open log.
- One **row** per folder, at most 10 (`config.MAX_FOLDERS`):
  - **Name**: an editable text box, starting as the folder's own name (the last part of its path).
  - The **path**, small, under the name, and **Remove**.
  - Two checkboxes: **Rename new files** and **Render into video**. A new row starts with Rename
    ticked and Render not.
  - With Render ticked: **Save video to** (a path box with **Choose**), and a line showing the
    loop's state (see What people see), with **Render now**.
- **Add folder** as today: a path box with Choose; Add, Enter, or straight after Choose. A folder
  already in the table is not added twice (`config.folder_key`).
- **Service times**, under the table: rows of *day*, *from*, *to* (e.g. Sunday 9:30am to 12:30pm),
  each with Remove, and **Add time**. Hint: "No video is rendered or swapped during these." Times
  are the computer's local time; a time can't run past midnight.
- Removing a row stops it at once. A render row's video is left in its save-to folder, so
  ProPresenter keeps playing the last one.

### Save checks
Each refuses the save, turns the field red and names the row; nothing is saved.
| Check | Message |
|---|---|
| A row with neither box ticked | Tick Rename new files or Render into video for Youth Media, or remove it. |
| Render ticked, no Save video to | Choose where to save Pre-service loop's video. |
| Save video to can't be found or written | Can't save into ProPresenter Loops. Check the folder is there and can be written to. |
| Save video to is a row's folder or inside one | Save Pre-service loop's video outside the folders Smart Explorer watches. It would end up renamed or inside its own loop. |
| A name a file can't have (empty, `\ / : * ? " < > \|`, a trailing dot or space, CON, NUL, COM1…) | A video can't be called "Pre:service". Use letters, numbers, spaces and dashes. |
| Two loops with the same name in the same save-to folder | Pre-service loop and Youth loop would both save Pre-service loop.mp4 in ProPresenter Loops. Give one another name. |
| Master on and no rows | Add a folder to watch first. (unchanged) |
| A folder that can't be found or opened | unchanged: names it |

### Save confirm
The existing confirm (files already in a newly added rename folder are left as they are) gains one
line per newly added or changed render row:
"Pre-service loop: 9 screens will become Pre-service loop.mp4 in ProPresenter Loops." plus "It
replaces the Pre-service loop.mp4 already there." when one exists. Changing a loop's name or
save-to folder renders it again under the new name; the old video is left where it was.

## Saved data
- `config.json` → `watch.rows`: a list of `{"path", "name", "rename", "render", "output"}`
  (strings and booleans; `output` may be `""`, and is kept when Render is unticked so ticking it
  again restores it). At most 10, one per `folder_key`.
- `watch.service_times`: a list of `{"day": 0-6 (Monday 0), "from": "HH:MM", "to": "HH:MM"}` with
  from before to. Bad entries are dropped when read.
- `config.watch_settings()` returns `rows` and `service_times`, plus, worked out from the rows:
  `folders` (the paths with Rename ticked, exactly what renaming reads today) and `loops` (the rows
  with Render ticked). Renaming code keeps reading `folders` unchanged.
- **Migration:** with no `rows`, the saved `folders` (or the older single `folder`) become rows with
  Rename ticked, Render off, named after the folder.
- **Going back:** Save also writes `watch.folders` (the rename paths), so 0.7.x still renames.
- `~/.smart-explorer/loops.json`, per loop (by `folder_key` of the source): the files behind the
  current video (`[name, size, mtime_ns]` each), the name and output it was saved as, when it was
  made, screens, length, files left out, and the last error. Written with `config.write_json`.

## When a render happens
1. **What goes in:** every file in the source folder (not subfolders) that `scanner.kind` calls an
   image or a video: PNG, JPG, JPEG, WebP, GIF, BMP, TIFF, HEIC, HEIF, MP4, MOV, M4V. PDFs and other
   files are left out.
2. **A change:** every look (5 s) compares the folder's files with the list in `loops.json`. An
   added, deleted, renamed or changed (size or modified time) file is a change. So is a missing
   video in the save-to folder, or a changed name or save-to folder.
3. **Settle:** a render starts once the folder has had no change for **30 s** and no file is still
   downloading (size and modified time held for `SETTLE`, as renaming does).
4. **Renaming first:** when the row also has Rename ticked, the render waits while that folder has
   new files waiting to be renamed or being renamed. Files renaming gave up on, or that are stuck
   in use, don't hold it up; they go in under the names they have.
5. **Start-up:** after the existing wait after start-up (none when started from the window), as for
   renaming. If nothing changed and the video is there, nothing renders.
6. **One at a time:** loops never render together; the next waits its turn, in the table's order.
7. **Service times:** no render starts during one. A render running when one begins is stopped
   (its files deleted) and runs again when it ends. A finished video waiting to go in waits too.
8. **No AI:** loops don't use OpenRouter. No key, no credit, no internet and the monthly limit pause
   renaming only. The watcher looks after loops on every look, before renaming and before any of
   its early returns, so a renaming problem or a long batch never holds a loop up.
9. **Render now** (the row's button) renders that loop on the next look whether or not anything
   changed. During a service time the window asks first ("It's a service time until 12:30pm.
   Render Pre-service loop now anyway?"); confirming renders straight away and swaps it in. Shown
   only when watching is on.

## The render (`loops.py`)
1. **Plan:** list the files, natural sort by name, read each:
   - a picture with Pillow (as `prep` does: HEIC through pillow-heif, turned the right way up from
     its EXIF, transparency flattened on black);
   - an animated GIF or WebP: its frames and their durations, with Pillow;
   - a video: its length and size from ffmpeg's header (as `prep.video_frame_b64` reads it).
   A file that can't be read is **left out** and named (see What people see).
2. **Lengths:** a picture 10 s; an animated picture its own length repeated to fill 10 s, or its own
   length if longer; a video its own length, held on its last frame to at least 2 s.
3. **Prepare** in the work folder `~/.smart-explorer/loops/<key>/`: each still as a 1920×1080 PNG on
   black, each animated picture as a short clip (its frames, fitted the same way).
4. **ffmpeg**, one run: each input fitted to 1920×1080 (scale down or up keeping its shape, black
   bars), square pixels, 30 fps, `yuv420p`, no audio; joined with 1 s `xfade` crossfades; the last
   screen crossfades for 1 s into the first screen's first frame, so the last frame matches the
   first. One screen: just that screen, no fades. Length = the sum of the lengths minus 1 s per
   crossfade between screens.
   Output: `libx264`, CRF 20, `-movflags +faststart`, `-an`. The filter graph is written to a file
   in the work folder: a long loop's command line would pass Windows' limit.
5. **Gently:** ffmpeg runs as a child process at low priority (Windows `BELOW_NORMAL_PRIORITY_CLASS`
   with no console window; Mac `nice`). The watcher checks it every look, reads its progress
   (`-progress`) for the percentage, and stops it after `max(10 min, 3 × the loop's length)`.

## The swap
1. ffmpeg writes into the work folder.
2. The finished video is copied into the save-to folder as `Pre-service loop.mp4.part`, a name
   ProPresenter doesn't import.
3. `os.replace` swaps it in as `Pre-service loop.mp4` in one step.
4. If Windows refuses (ProPresenter has the file open), the `.part` stays and the swap is tried again
   every **60 s**, never during a service time (unless Render now was confirmed during it). After
   **10 minutes** of refusals it says so once.
5. Only after the swap works: `loops.json` is updated, the work folder emptied, and "updated" said.
   A `.part` left by a crash or switch-off is deleted before the loop's next render.

## What people see
### The row (Settings)
| State | Line |
|---|---|
| Up to date | Pre-service loop.mp4 · 9 screens · 2 min 05 s · made 8:14am |
| Change seen | Changed. Rendering in 25 s, in case more are on the way. |
| Rendering | Rendering… 40% |
| Held | Will render after the service, at 12:30pm |
| Waiting to go in | New video ready: waiting for ProPresenter to let go of the old one |
| Failed (red) | Last render failed: the disk is full. Trying again at 9:05am. |
| Not made yet | Not rendered yet |

### Status bar (main window)
One line, as today: a problem first, then work, then all good.
- Pre-service loop changed. Rendering in 25 s, in case more are on the way.
- Rendering Pre-service loop… 40%
- Pre-service loop will be updated after the service, at 12:30pm
- New Pre-service loop is ready: waiting for ProPresenter to let go of the old one
- Watching 3 folders · loops up to date (renaming's own texts otherwise unchanged)

### Notifications (`notify`, as renaming's)
| When | Text |
|---|---|
| Swapped in | Pre-service loop updated: 9 screens, 2 min 05 s. |
| A file left out | Pre-service loop: couldn't use Cafe.png, so it was left out. The other 8 screens are in the video. |
| Render failed | Couldn't update Pre-service loop: the disk is full. The old video is still in place. Smart Explorer will try again in 5 minutes. |
| Folder empty | Pre-service loop's folder is empty, so the old video was kept. |
| Source missing / can't open | Smart Explorer can't find the folder for Pre-service loop. Check Google Drive is running and signed in. (after `FOLDER_GRACE`, as renaming) |
| Save-to missing / can't write | Smart Explorer can't save Pre-service loop into ProPresenter Loops. Check the folder is there. |
| In use 10 minutes | ProPresenter is still using Pre-service loop.mp4. The new one goes in as soon as it stops playing. |

Each problem is said once and again only after it cleared and came back, as `PROBLEMS` are. A
failed render is tried again after 5 then 30 minutes (`RETRY`), and on the next change.

### Log
Every render: the files in and left out, the length, how long it took; on failure the last 20
lines of ffmpeg's output. Open log opens it, as today.

## Window API
- `GET /api/watch` → `settings.rows`, `settings.service_times`; `state.loops` from `status.json`
  (per loop: `path`, `state`, `progress`, `text`, and the up-to-date details).
- `POST /api/watch/preview {"rows": [...]}` → per row: files already in a new rename folder, and for
  a render row the screens it would use and whether its video already exists.
- `POST /api/watch {"rows": [...], "service_times": [...], ...}` runs the Save checks, records newly
  added rename folders, saves, then starts or stops the background process as today (it runs when
  watching is on and there is at least one row).
- `POST /api/loops/render {"path": source}` leaves a request file the background process takes on
  its next look (as Try again does); 409 when watching is off.
- `/api/rename`: unchanged (renames in the window inside a rename row's folder join its known list).

## Rig test (build step 2)
A hidden option `Smart Explorer.exe --loop-test "<folder>"` makes "Smart Explorer loop test.mp4" in
that folder: a few coloured screens reading "Loop test · Version 1". Each later run renders Version
2, 3… and swaps it in with the real swap, trying for up to 2 minutes, then reports by notification
("Loop test: Version 3 is in place" or "Loop test: Version 3 couldn't go in: the old one is in use").

Fynn, at church, outside service times, with the PR's Windows installer (CI attaches it to every PR):
1. Make an empty test folder and point a new smart playlist at it. Run the test once; the playlist
   shows Version 1.
2. Run it again; check the playlist still lists the video and plays Version 2.
3. Play the loop in ProPresenter and run it again: note whether the swap is refused, then whether
   Version 3 goes in once playback stops.
4. Note how long the render took (in the log).
If step 2 fails, stop and choose a fallback before build step 3.

## Tests
Unit tests (pytest, throwaway HOME, never the real `~/.smart-explorer`; ffmpeg faked except where
marked):
- Rows: migration from `folders` and `folder`, dedupe, 10 at most, every Save check, `folders` still
  written, bad service times dropped.
- Changes: added, deleted, renamed and edited files each render; nothing changed renders nothing;
  the 30 s settle; a downloading file waits; a rename row waits for renaming but not for given-up or
  stuck files; a missing video renders; a new name or save-to renders.
- Service times: no start during one; a running render is stopped and redone; a finished swap
  waits; it renders when the time ends; Render now during one renders.
- The plan: natural sort; lengths for pictures, animated pictures (shorter and longer than 10 s),
  short and normal videos; crossfade offsets and total length; one screen; a file left out; an
  empty folder keeps the old video.
- The swap: refused (`PermissionError`) then tried every 60 s and said once at 10 minutes;
  `loops.json` only changes after it works; a stale `.part` is cleared.
- No key, no credit, offline and the monthly limit don't stop loops; a long rename batch doesn't
  stop a render from being checked.
- Texts for the row, the status bar and notifications.
Real renders (bundled ffmpeg, in CI on Windows and Mac): a fixture folder of a portrait PNG with
transparency, a HEIC, an animated GIF, a short MP4 with sound and a normal MP4. Checks: H.264 and
`xfade` present; 1920×1080, 30 fps, no audio stream; the expected length to 0.1 s; the last frame
matches the first.
Smoke: `scripts/smoke_loops.py` on the built Mac app and the built Windows app in CI: drop screens
in a loop folder, expect the video; change one, expect a new render; on Windows hold the video open
and expect the swap to wait, then go in once let go.

## Build order
1. `loops.py`: plan, prepare, ffmpeg, the swap; unit tests and real renders in CI.
2. `--loop-test` and the rig test. Stop here if the smart playlist drops the swapped video.
3. `config`: rows, service times, migration; `app.py` endpoints and Save checks.
4. `watch.py`: loops on every look, settle, service times, one render at a time, the swap retry,
   no-AI independence, texts.
5. The window: Folders table, row lines, Render now, service times, status bar.
6. `scripts/smoke_loops.py` in CI; README, the volunteer page, this spec's references;
   `LOOP_BUILDER.md` (where it lives, fixed names, link here) and CHURCH.md's Smart Explorer row.
7. Version 0.8.0, PR (Auto-fix on), CI green on Windows, merge, tag, release.

## Not in this version
A different picture length or transition per loop · music · subfolders · other sizes than 1920×1080
· changes to Runsheet Pilot (it finds the loop by its fixed name) · rendering from the window when
watching is off.

## To check on the rig
- The smart playlist keeps a video swapped in under the same name, and plays the new one (rig test).
- Whether ProPresenter holds the video open while it plays, and what it does when it is swapped
  while not playing.
- How long a render takes on the PC, and whether ProPresenter and the livestream stay smooth while
  one runs outside service times.
- Service times to enter: Sunday 8:00am to 3:00pm (Fynn, 6 Nov). Friday youth nights also use the
  PC: confirm whether they count.
