# The Sunday check: has Smart Explorer done its job this week?

Asked for by Fynn on 10 Nov 2026: "a Sunday person can just look for a green check mark ... Hey, has Smart
Explorer done its job?" Approved from a mockup ("yes to both, build it"), with one condition: "I don't want people
relying on this if it's wrong". So it ticks only what it can see for itself, says when it can't tell, and says in
plain words what a tick doesn't mean.

## Where

The start screen's first half ("Rename by itself") while watching is on. Off, it shows the intro as before. It
follows the window's look at the background copy, every 5 seconds (`/api/watch` → `sunday`).

## The week

It begins when the last service time ended (Sunday 8am to 3pm: last Sunday 3pm; during a service, the one
before). With no service times, the last 7 days. With several service times, the latest to have ended.

## One line per folder (`sunday.py`)

| Folder | Tick | Amber | Working | Red |
|---|---|---|---|---|
| Slide folder | something new this week, nothing waiting to be named | nothing new (only if *Changes every week* is ticked) | files waiting to be named | can't find or open the folder; files waiting while renaming is paused (no key, no credit, the limit, no internet) |
| Loop | the video was made this week | same video as last week (only if *Changes every week*); its folder is empty | rendering, waiting for quiet, held for a service, not made yet | the render failed, the folder is missing |

Plus a red **Google Drive** line when Drive isn't running. The headline: any red, "A problem to fix"; else any
amber, "One thing to check before Sunday"; else any working, "Working on it"; else **Ready for Sunday**.
Overriding all of it: "Smart Explorer isn't watching" (red) when the background copy isn't running, and "Can't
tell right now" when it hasn't checked in for 90 seconds. Under the lines: the last 4 files named (the watcher
keeps 20 in `watch/recent.json`), and "It checks that new files arrived and were named, not that they're the
right ones."

**New this week** means a file in the folder whose creation time on this computer (when Google Drive downloaded
it; Windows' creation time, a Mac's birth time) or modified time (an updated slide synced under the same name) is
after the week began. Nothing is stored for it. Where it can be wrong, it errs towards amber: a file copied in with
its old dates keeps them. One way it could tick wrongly: Google Drive downloading everything again (a reinstall)
makes every file look new.

## A second line: what it's doing now (added 10 Nov)

Fynn added a folder of old images and couldn't tell whether it was "sending those to the AI ... or waiting a
couple of minutes". So each slide folder's line has a small second line:
- What the background copy is doing with it now, from `folder_states` in status.json (the watcher writes one per
  folder every look): "Watching, nothing waiting", "Waiting for 2 files to finish downloading", "2 new files found:
  renaming in 40 s, in case more are on the way", "Renaming 2 files now", "renaming is paused", stuck or given up.
  Left out when the background copy isn't running, rather than shown stale.
- How many files are in it, and "none new since …" when none are.
- When the folder was added, if this week: "added 4:21pm: files already in it were left as they are"
  (`known.recorded`, set when watching began for it).

## At a glance (10 Nov, later)

"Make it super super clear so a volunteer can look at this at a glance without reading the little grey text."
Each folder is now one line: a coloured icon, its name, and a pill with a word or two (`short`): Ready, Ready,
3 new, Nothing new, Naming 2, Downloading, Paused, Folder missing, Making video, After the service, Video failed,
Empty. The sentences above (`text`, `detail`) and the Latest list only show under **Details**. The headline says
"Since Sunday 12:00pm", and one short line under the folders keeps the honest part: "Checks that files arrived and
were named, not what's in them."

## Changes every week

A tick on each folder on the folders map, on by default (`weekly` in the row). Untick it for a folder that stays
the same (Service slides: giving, welcome), so it isn't amber every week and people don't learn to ignore amber.

## The map's colours

Orange for the loops read as a problem ("Orange makes me think that there's something wrong"). After a
neutral try, Fynn asked for colour by place instead: Google Drive blue, Smart Explorer purple, ProPresenter
green ("I liked having the green boxes"). Amber and red never appear on the map, so on the start screen they
only ever mean a problem. The start screen also hides the naming tools (Choose folder, the path box, the
naming style, Keep order) until a folder is loaded: they belong to "Rename a folder now".
