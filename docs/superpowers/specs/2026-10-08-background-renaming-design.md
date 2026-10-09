# Smart Explorer — Background renaming (watch a folder) design

## Goal
On the church's Windows PC, Smart Explorer runs with no window from the moment
someone signs in, watches one folder that Google Drive keeps in sync, and renames
every **new** file in it with the normal naming logic, with nobody involved.
ProPresenter's playlist on that folder then shows the new files under their new
names.

The typical week: people drop Canva exports and videos into the shared Drive
folder during the week. On Sunday at about 8am the PC is turned on, Drive brings
the week's files down, Smart Explorer names them, and they are in ProPresenter,
properly named, before the service. Nothing should arrive during a service, so
there is no quiet time.

## Decisions made in brainstorming
| Question | Decision |
|---|---|
| Which files are renamed | **New files only.** Files already in the folder, and files Smart Explorer has named, are never renamed. Existing names are passed to the AI as taken, so new names fit in and never clash. |
| When it runs | The whole time the PC is on. The start-up catch-up is the main job. |
| Folder layout | **Rename in place.** People drop files straight into the folder ProPresenter watches. (Not an Inbox subfolder, not copies elsewhere.) |
| How it reports | **Windows notifications**, plus a status bar in the window when it is opened. No tray icon. |
| Retries | Charge-aware: work already paid for is kept, at most 2 paid attempts per file per start-up, free checks before any paid request. |
| Bible references and times | Unchanged: full stops (`John 3.16`, `10.30am`). Windows does not allow `:` in file names. |

## Not in this version
Undo for automatic batches (journals are still written, so it can be added) ·
quiet time · subfolders · context text per batch · tray icon · per-folder
naming prompts.

## How it runs
- **Background mode.** `Smart Explorer.exe --watch` (from source: `python desktop.py --watch`)
  runs the watcher: no window, no web server, no console window. It shares all
  naming code with the window, so the key, model and prompt edits in Settings
  apply to both. It reads the config on every loop, so changes made in the window
  take effect without a restart.
- **One copy at a time.** The watcher holds an OS file lock on
  `~/.smart-explorer/watch/lock` (`msvcrt.locking` on Windows, `fcntl.flock`
  elsewhere) for as long as it runs. A second copy that cannot take the lock
  exits at once. A crashed copy leaves no stale lock.
- **Stopping.** The window asks the watcher to stop by creating
  `~/.smart-explorer/watch/stop`. The watcher checks for it every loop, deletes
  it and exits.
- **Start by itself when the computer starts** (Settings checkbox). Smart Explorer
  adds itself to the computer's start-up items, so nobody adds it by hand. On
  Windows: a shortcut `Smart Explorer (background).lnk` in the user's Startup
  folder (`shell:startup`) runs `Smart Explorer.exe --watch` (PowerShell
  `WScript.Shell`, no window, no administrator rights). On a Mac: a login item, the
  LaunchAgent `~/Library/LaunchAgents/com.jimhoggey.smartexplorer.watch.plist`
  (`RunAtLoad`). Either runs at **sign-in**: if the PC signs in automatically, that
  is start-up; otherwise it starts when someone types the password, which they do
  anyway before opening ProPresenter.
- **Started from the window** (turning watching on, the Start button) the watcher
  runs with `--watch --now`: the computer is already up, so there is **no start-up
  wait**. Only a start with the computer waits.
- **Updates.** Before running the installer, the in-app updater creates the stop
  file and waits up to 10 s for the watcher to release its lock. The installer
  starts `Smart Explorer.exe --watch --now` again afterwards when the Startup
  shortcut exists. The uninstaller removes the shortcut.
- **Mac.** Notifications go through `osascript`.

## Spotting new files
The watcher looks at the top level of the folder every **5 s**. It skips hidden
files, Google Drive's temporary download files (`~$*`, `*.tmp`, `.~*`,
`desktop.ini`) and anything `scanner.kind()` does not read.

**The known list** (`~/.smart-explorer/watch/known.json`, per folder) holds, for
every file Smart Explorer knows, its name (lower case) and its print: size and
modified time in whole seconds. A file is **new** only if **both** its name and
its print are unknown. So:
- a file Smart Explorer named is never renamed again (its new name is added);
- a file someone renames by hand is not renamed (its print is known);
- an updated slide uploaded under the same name is left alone (its name is known).

**Turning watching on** records every file already in the folder in the known
list, without reading them, so they are left as they are. When the window renames
files inside the watched folder, it adds them to the known list too. If the
watcher ever finds **no record** for its folder (known.json deleted, damaged by a
power cut, or the folder changed by hand), it records the folder the same way
first: it never renames a whole existing folder.

A waiting file that someone **renames by hand** (same print, new name) is recorded
and left alone. A known file's **name is forgotten** once the file has been gone
from the folder for 10 minutes, so next week's `1.png` or `Untitled design.png` is
new again; a file back within that time (Drive replacing it) stays known.

**Waiting for Drive.** A new file is **ready** when its size and modified time
have not changed for **10 s** and it can be opened for reading. (In Drive's
stream mode, opening the file also makes Drive download it.)

**Batches.** Files that arrive together are named together, so a set is named
consistently, look-alikes are told apart and Keep order can number it.
- **Wait after the computer starts** (a setting, default **3 minutes**, 0–30,
  shown only when "Start by itself" is ticked): after a start with the computer
  the watcher names nothing for this long, so Drive can bring the whole week down
  first. It keeps tracking files during the wait. A start from the window skips it.
- After that, a batch starts when there are ready new files and **no new file has
  appeared or changed** for **60 s** (the first batch after start-up) or **20 s**
  (any later batch).
- At most **200 files** per batch; the rest go in the next batch.

## Naming
- The batch uses the watch folder's naming style (ProPresenter by default) and
  the key, model and prompt edits from Settings. There is no context text.
- `existing` is every other file name in the folder, as in the window
  (`scanner.siblings`).
- **Keep order.** The rule that decides whether files are numbered in sequence
  (`looksNumbered` in `static/app.js`) moves to Python as
  `scanner.looks_numbered(items)`. `/api/scan` returns it as `numbered`, and the
  window uses that instead of its own copy. The watcher applies the same rule to
  each batch. When it is true, names get `01 `, `02 `… in front, per folder, in
  natural order, with at least two digits (the window's `numberItems`). A number
  that is already taken in the folder from an earlier week gets ` (2)` from the
  renamer, as in the window.
- **Paid work is kept.** `namer.run` is split so its two steps can be called on
  their own: `namer.read_all(...)` (the paid image-reading step) and the naming
  step (`name_all`, already separate). Descriptions are kept in memory against
  each file's print. When the naming step fails, the retry only reruns naming.

## Renaming
- Just before renaming, each file's print is checked again. A file whose print
  changed since it was read is dropped from the batch and goes back in the queue
  as a new file.
- Renames go through `renamer.plan` and `renamer.apply`, as in the window: no
  overwrites, ` (2)` on a clash, an undo journal in `~/.smart-explorer/journal/`.
- Each renamed file's new name and print go into the known list.
- **Never rename with a guess.** When the naming step fails, `name_all` falls back
  to the file's raw words for a person to fix. The watcher does not rename those
  files. They wait and are retried.

## Failures and cost
- **Free check first.** Before every paid batch, the watcher calls OpenRouter's key
  check (`GET /api/v1/key`, as Settings' *Test key* does; also `GET /api/v1/credits`
  if OpenRouter accepts the app's key there, to be confirmed in the build). It
  costs nothing. When it fails, no files are sent:
  - **No connection:** one notification; check again every 5 minutes.
  - **Key rejected or out of credit:** one notification saying what to do; check
    again every 15 minutes. Requests OpenRouter refuses for these reasons are not
    charged either.
- **At most 2 paid attempts per file per start-up.** A paid attempt is a batch
  sent after the free check passed. After the second failure the file is left
  under its old name until the watcher next starts, and a notification names it.
  Counts are kept in memory, so they reset at the next start-up.
- **One file cannot be read** (damaged, unusual format): it is tried again after
  5 minutes and after 30 minutes, then given up with a notification. Turning a
  file into images happens on the PC and costs nothing; a file the model fails
  to describe also uses up one of its 2 paid attempts.
- **Monthly limit** for background naming (a setting, default **US$5**, about
  1,000 slides with the recommended model). Before each batch, when this month's
  background spend has reached the limit, the watcher pauses and notifies. A
  batch can go over by at most one batch (≤200 files).
- **Folder not found or can't be opened** (Drive not ready, signed out, restarting,
  drive letter missing): the watcher waits quietly until the start-up wait is over
  plus 2 minutes, and mid-run until the folder has been gone for 2 minutes (so a
  Drive restart during a service says nothing), then notifies once. A folder it
  can't list is a problem ("can't open"), never an empty folder.
- **A local failure after paying** (a full disk, an undo record that can't be
  written): the paid descriptions are kept first, spending that can't be recorded
  is logged, and anything else that goes wrong in the batch counts as a paid
  attempt, so it can never repeat every 5 seconds.
- **A refusal while naming** (402 or 401 after the files were read) counts like a
  refusal while reading: no attempt is used, the descriptions wait.
- Each problem notifies **once**, and again only after it has cleared and come back.

**Spending records.** The watcher records its own spend in
`~/.smart-explorer/watch/spend.json` (`{"2026-10": 0.12}`), which only it
writes. The window's cost display in Settings adds it to its own totals. So the
watcher never writes `config.json`. `known.json` is the one file both write (the
window on turn-on and after its own renames, the watcher after each batch), always
atomically.

**Safe settings.** `config.save` writes a temporary file and swaps it in with
`os.replace`, so the watcher can never read a half-written `config.json` (it
would take that as "no key").

## Notifications
Plain words, no version numbers. `<Folder>` is the folder's name.
| When | Text |
|---|---|
| Watcher starts | Smart Explorer is watching <Folder>. New files will be renamed in 3 minutes. |
| Start-up wait over, nothing new | Checked <Folder>: no new files. |
| Batch starts | Renaming 12 new files… |
| Batch done | 12 files renamed and ready for ProPresenter: Giving, Sermon - Anchored Wk 3, Welcome and 9 more. |
| Batch done with failures | 11 files renamed and ready for ProPresenter. 1 couldn't be named yet: 7.png |
| No connection | Smart Explorer can't reach the internet, so new files aren't renamed yet. It will try again by itself. |
| Key rejected | OpenRouter didn't accept the key. Open Smart Explorer → Settings to fix it. |
| Out of credit | OpenRouter is out of credit. Add credit at openrouter.ai; Smart Explorer will try again by itself. |
| Monthly limit reached | Background renaming has reached this month's US$5 limit. Raise it in Settings to carry on. |
| File given up | Couldn't name 7.png. It's still in <Folder> under its old name. |
| Folder not found | Smart Explorer can't find <Folder>. Check Google Drive is running and signed in. |
| Google Drive not running | Google Drive isn't running on this computer, so new files can't arrive in <Folder>. Open Google Drive; Smart Explorer carries on by itself. |

**Google Drive check.** When the folder's path is in Google Drive (`My Drive`,
`Shared drives`, `Google Drive`, `GoogleDrive-…`), the watcher asks every 30 s
whether Google Drive for desktop is running: `tasklist` for `GoogleDriveFS.exe`
on Windows, `pgrep -x "Google Drive"` on a Mac. It cannot see Drive's sync
progress (Drive offers no way to ask). Off for the start-up wait plus 2 minutes, and
for 2 minutes in a row: it says so once, the bar turns red ("Watching <Folder> ·
Google Drive isn't running", state `warning`), "Checked: no new files" is not said,
and renaming carries on. It clears when Drive runs. Can't tell: nothing is said.

**Windows:** a toast through Windows' own notification API, shown by PowerShell
(built into Windows 10 and 11) started with `CREATE_NO_WINDOW`, so nothing flashes
on screen. The installer gives the Start menu shortcut an AppUserModelID
(`jimhoggey.SmartExplorer`) so toasts carry Smart Explorer's name and icon; run
from source they show under PowerShell's name. **Mac:** `osascript -e 'display
notification …'`. A notification that fails to show is logged and otherwise
ignored.

## Status and log
The watcher writes `~/.smart-explorer/watch/status.json` on every loop:
`{state, message, since, heartbeat, last_batch: {at, count}, problem}`.
`state` is one of `waiting` (start-up wait, with time left), `downloading`
(files not ready yet), `renaming`, `watching`, `paused` (a problem).

**The window** shows a status bar across the top of the main screen whenever
watching is on, read from `GET /api/watch` every 5 s:
- Waiting for Google Drive, 2 min left
- Renaming 12 files…
- Watching Sunday Media · last batch 8:04am, 12 files
- Paused: out of OpenRouter credit
- **Background renaming isn't running** (no heartbeat for 30 s) with a **Start** button.

**The log** `~/.smart-explorer/watch/watch.log` records each start, batch, rename
(old → new), problem and stop, one line each with the time. It rolls over at
1 MB, keeping one old file.

## Setup in Settings: "Watch a folder"
- **Watch a folder** on/off.
- **Folder** with *Choose folder*: the Drive folder ProPresenter's playlist watches.
- **Naming style:** ProPresenter by default.
- **Monthly AI limit** in US$ (default 5), with this month's background spend below it.
- **Start by itself when the computer starts** on/off (Windows and Mac), with a line
  that never claims more than is true. Ticked but not saved: "Click Save, and Smart
  Explorer adds itself…". Saved: the server reads the entry back (`autostart_on`)
  and only then the line turns green, "✓ Smart Explorer is in this computer's
  start-up items", with **Show** (the Startup folder on Windows, Login Items on a
  Mac). If adding it failed: an error, and "isn't in the start-up items yet". On a
  Mac, Save also registers the login item with launchd at once (`launchctl
  bootstrap`), so it is listed straight away, not only after a restart. Off: "it
  runs until the computer restarts".
- A Save that can't be done (no folder, a folder that can't be found or opened)
  marks the folder box red and says "Nothing was saved yet."
- **Wait after the computer starts** in minutes (default 3), shown only when the
  box above is ticked, saying that turning it on here starts straight away.
- **Status line** (as the status bar) and **Open log**.

While a batch waits out its quiet minute the bar says "Found 1 new file. Renaming
in 45 s, in case more are on the way."

Turning watching on shows "34 files already in this folder will be left as they
are", records them in the known list, saves the settings and starts the watcher
straight away. Turning it off creates the stop file and removes the Startup
shortcut. Changing the folder records the new folder's files the same way.

Settings live in `config.json` under `watch`:
`{enabled, folder, profile, startup_wait_min, monthly_limit_usd, autostart}`.

## Modules
| File | Change |
|---|---|
| `watch.py` (new) | The loop: scan, known-list check, readiness, start-up wait and quiet gap, batches, free check, attempts, limit, status file, log. Clock, scan and naming are passed in, so tests run it without sleeping or OpenRouter. |
| `known.py` (new) | The known list: load, save (temp file + `os.replace`), record a folder, add, is-new. |
| `notify.py` (new) | `notify(title, text)` for Windows (PowerShell toast) and Mac (`osascript`); never raises. |
| `autostart.py` (new) | Create, remove and check the Startup shortcut; no-ops off Windows. |
| `desktop.py` | `--watch` runs the watcher under the single-instance lock. |
| `namer.py` | Split `run` into `read_all` + naming; `run` keeps its behaviour for the window. |
| `scanner.py` | `looks_numbered(items)` and `order_numbers(items)` (ported from `app.js`). |
| `config.py` | Atomic `save`; `watch_settings()` with defaults. |
| `app.py` | `GET/POST /api/watch` (settings, status, known-file count preview, start, stop); `/api/scan` returns `numbered`; spend totals include `watch/spend.json`; renames inside the watched folder are added to the known list. |
| `updater.py` | Stop the watcher before installing. |
| `static/index.html`, `app.js`, `style.css` | Status bar, "Watch a folder" Settings section; use `numbered` from the scan. |
| `packaging/windows-installer.iss` | AppUserModelID on the Start menu shortcut; restart the watcher after an update when the Startup shortcut exists; remove the shortcut on uninstall. |
| `README.md`, `docs/` | A "Background renaming" section; a one-page volunteer note (what the notifications mean, what to do when stuck). |

## Testing
Automated (pytest, no OpenRouter: `namer.mock_run` and stubbed HTTP, a fake clock):
- **New files:** a file renamed by hand, a file replaced under the same name, Drive
  temporary files and hidden files, the turn-on record, renames made in the window.
- **Readiness and batches:** a file still growing is not read; the start-up wait;
  the 60 s and 20 s quiet gaps; the 200-file cap; a file changed between reading
  and renaming goes back in the queue.
- **Keep order:** the Python `looks_numbered` passes the same cases as the
  window's (`1.png…14.png`, `Slide1…`, `Sermon.001…`, `01 …`, camera numbers
  rejected, gaps allowed) and the window uses it.
- **Cost:** a failed naming step reruns naming only (no second read); 2 paid
  attempts then give up; free-check failures never send files; refused requests
  do not count; the monthly limit pauses; a fallback name is never applied.
- **Processes:** a second watcher exits; the stop file stops it; status and
  heartbeat; `config.save` is atomic; Startup shortcut created and removed
  (Windows CI only).
- **Notifications:** the texts above for each event, each problem once.

On a Mac: run `python desktop.py --watch` on a test folder with `SMART_EXPLORER_MOCK=1`,
drop files in, watch the status bar and notifications.

**On the church PC, outside service time** (booth rule: no changes during a service):
1. Google Drive syncs the folder onto the PC. Note whether it is in stream or
   mirror mode. A renamed file syncs back to Drive under its new name, and its
   modified time is unchanged after the rename.
2. **ProPresenter's playlist** on that folder shows a renamed file under its new
   name and leaves no missing item behind. This is the main unknown of renaming in place.
3. Notifications appear on the PC, and Focus Assist does not hide them.
4. The PC signs in by itself, or note who signs in, so the watcher starts at 8am.
5. An update stops the watcher, installs, and starts it again.

## Open questions for the build
- Does OpenRouter's `/api/v1/credits` accept a normal key? If not, the free check
  covers connection and key, and an out-of-credit refusal (HTTP 402, not
  charged) is the credit check.
- Does the installer's Restart Manager close a windowless process? The updater
  stops the watcher first anyway; a hand-run installer may need `taskkill` in
  `PrepareToInstall`.
- Is the modified time kept through a rename on Drive's stream-mode drive? If not,
  prints fall back to size plus the first 64 KB's hash.
