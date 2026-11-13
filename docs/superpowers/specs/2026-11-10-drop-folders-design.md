# Drop folders: ProPresenter never sees a file renamed

Fynn, 10 Nov 2026: last time ProPresenter showed "a question mark on the icons, on the images", and each had to be
remapped by hand to its new name. ProPresenter knows media by its file path, so a file it already uses goes
missing once it is renamed. (What Fynn saw; not yet tried on the rig on purpose.) Approved: "yes build the drop
folders".

## How it works

- A slide folder's row can have **move_to**: the folder its smart playlist links. The office drops files in the
  drop folder ("Announcements - drop here"); the watcher names each one and moves it to move_to in the same step
  (`renamer.plan` with `dir`). ProPresenter only ever links move_to, so it never sees an unnamed file, and nothing
  it knows is ever renamed.
- Without move_to a row is named where it is, as before (the folders saved before this keep working).
- A file moved on is not remembered in the drop folder: the same file dropped again later is new again and moves
  on too (a "(2)" is added where the name is taken). Files already in a drop folder when it was added stay there,
  and the Sunday check says so ("3 left in the drop folder from before it was added").
- Into another disk, the file is copied beside its new name as `.part`, swapped in, then the old one deleted; if
  that can't be deleted (in use), the copy goes again, so a file is never in both places.
- Save refuses move_to when it is the drop folder itself, a folder Smart Explorer watches (it'd be named again),
  or (watching on) missing or not writable.

## On the map

The ProPresenter box for each slide folder shows "Smart playlist: <move_to>" with Change folder. Without one it
says "Renamed where it is, so ProPresenter can lose track of a file it saw first" with **Choose a folder for named
files**. The Smart Explorer box says "Then moves it to a different folder". The office's sentences name both
folders ("Drop it in Announcements - drop here … moves it to Announcements"); old ones are deleted from move_to,
which is why move_to should be synced with Google Drive too (unlike the video folders).

## The Sunday check

A drop folder's line judges what reached move_to this week (that is what ProPresenter shows); what waits to be
named is in the drop folder.
