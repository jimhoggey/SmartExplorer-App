# How it works: a flow diagram and set-up steps in Settings

Approved by Fynn on 9 Nov 2026, after two mockups: the first (a diagram plus a live checklist that did the
set-up in place) was "way too convoluted". The aim is one simple flow a volunteer can read at a glance.

## The idea it has to get across

The office only ever touches Google Drive: drop each slide or screen in the right folder, drop it in both if it's
used in two places, delete what's finished with. Everything after that happens by itself. Drive decides what
Smart Explorer sees, so what RunsheetPilot sees, so what ProPresenter uses.

## What it is

**Changed 10 Nov 2026 (Fynn, after trying it):** the map is now where folders are set up. It replaces the Folders
table and its path box: "I should be able to just open up the graph and add folders there". Each folder also gets
a name of its own, which needn't match the folder's ("Each folder's name may not be the name in the file path").

- **Set up folders** on the start screen, or *Settings → Folders → Open*, opens the **folders map** on top of
  Settings, which stays open. **+ Add a folder** in a row of the Google Drive column adds a slide folder (top row,
  Rename new files) or a loop folder (bottom row, Render into video); its name box sets the row's name (a loop's
  is its video's name); **×** takes it out of that row. Each loop's video has its own box in the ProPresenter column
  ("Pre-service loop.mp4 · Smart playlist: ProPresenter Loops"), and its own **Choose** / **Change folder**, so
  two loops can go to two folders (Fynn, 10 Nov: one box per folder didn't allow that). A new loop starts with
  the folder the other videos go to, when they all go to one. **Save** saves them as Settings' Save
  does (the same checks; a folder Save rejects is marked red), with *Watch these folders by itself* beside it.
  **Cancel** or Escape puts back what was there. Drawn in HTML, not SVG, so names are real text boxes.
- *Settings → Folders* keeps a list to read: each folder's name, what it does, and a loop's line with Render now.
- The start screen shows both ways in: **Rename by itself** (watched folders, the main use) and **Rename a
  folder now** (drop or choose a folder in the window).
- There is no switch for a folder that is both renamed and a loop: such a row (from before) shows in both rows of
  the map, and × takes it out of one.
- **The diagram:** the office at the top, then Google Drive, Smart Explorer and ProPresenter, then RunsheetPilot.
  - Slide folders (Rename new files): one step, "Names each new file", in the same folder, one playlist each.
  - Loop folders (Render into video): two steps, "Makes one video" and "Saves the video" to a different folder,
    because that's two jobs and the second is what people get wrong. Their screens aren't renamed.
  - The real folder names from the table, with examples (Preach, Announcements, Service slides, Pre-service,
    Post-service) until there are some. A row with both ticks is in both lanes.
- **What the office does** buttons light up the path a file takes and say it in a sentence: new announcement,
  change or remove one, used in two places, birthday screen (not an announcement, so it goes in the loop).
- **Set it up once** buttons light up one column and show its steps. Hidden until clicked, so the diagram stays clean.

## What it leaves out, on purpose

Live ticks, manual ticks, doing the set-up inside the guide, opening by itself on first run.

## What the wording rests on

- **RunsheetPilot** (its code, `propresenter/media_bin.py`, `media_match.py`): reads every Media Bin playlist,
  inside folders too; code narrows the folders, then its AI picks the file for each run sheet line by name.
  So the names Smart Explorer gives are what make it work.
- **Renaming** (`known.py`): a file is new only if its name and its size and modified time are both unknown. A
  new name gets named. A file put back under a known name keeps it. The exact same file put back later isn't
  renamed either: left as it is, since the case that matters (this week's file replacing last week's) works.
- **ProPresenter** (Renewed Vision's help): + at the lower left of the Media Bin, New Smart Playlist, choose the
  folder. Google Drive's clicks come from the 27 Oct check at church plus outside guides.

## Not yet checked at church

Both labels above against the church PC; a renamed file reaching the smart playlist and syncing back to Drive; a
file replaced under the same name staying in the playlist (it dropped out on 22 Oct; `--loop-test` covers videos).
