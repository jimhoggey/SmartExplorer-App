# Naming convention

Smart Explorer names files with one of two conventions, picked with the **ProPresenter / Photos & files** switch. The AI follows the text in [`conventions.py`](../conventions.py); this page is the human-readable version, so a media team can name files the same way by hand.

## ProPresenter

ProPresenter shows the file name under each thumbnail in the media bin, where long names get cut off, and finds media by searching names. So names are short, start with the thing that matters, and stay the same from week to week.

**Format:** `Category - Subject - Detail`

| Part | What goes in it | Examples |
|---|---|---|
| Category | Exactly one word or phrase from the list below. Always first, so files group together and a search for "Giving" finds every giving slide. | Giving, Sermon, Announcement |
| Subject | The specific thing: event, sermon series and week, song, Bible reference, or the slide's own short heading. Left out only when it would repeat the category. | Youth Camp 2026, Anchored Wk 3, Amazing Grace, Thanks For Coming |
| Detail | Only when another file in the batch would otherwise get the same name. | Love Offering, Bank Details, Point 1 Hope Holds, Verse 1, Portrait |

**Look-alikes.** A file with no look-alike gets no Detail: if there is one giving slide, it is just `Giving`. When two files would share a name, the Detail comes from the words that differ between them, taken from the files themselves: a second giving slide that says "Love Offering" becomes `Giving - Love Offering`, next to plain `Giving`. Only when the wording is the same does the Detail describe what else differs (`Giving - Bank Details`, `QR`, `Portrait`). The plainest file of a set keeps the bare name.

**Categories:** Welcome · Closing · Countdown · Announcement · Giving · Sermon · Scripture · Worship · Prayer · Communion · Baptism · Connect · Kids · Youth · Background · Lower Third · Bumper · Social · Other

**Style**

- Title Case, `" - "` between parts, at most 60 characters (aim for 40).
- Bible references and times use a full stop, not a colon: `John 3.16`, `10.30am`. Colons are not allowed in Windows file names.
- Dates are day then month: `Sun 19 Oct`, `3-5 Oct`.
- Sermon slides: `Sermon - Anchored Wk 3` for the series slide, `Sermon - Anchored Wk 3 - Point 1 Hope Holds` for the rest. Verses, quotes and points in the sermon's design belong to the sermon, not to Scripture.
- Song lyrics: `Worship - Song Title - Verse 1`, using ProPresenter's section names (Verse 1, Pre-Chorus, Chorus, Bridge, Tag, Ending).
- Countdowns give their length: `Countdown - 5 Min`.
- The same design in several sizes gets `Portrait`, `Square` or `Ultrawide`; the 16:9 version gets no size.
- Never: file extensions, sequence numbers, or the words Slide, Image, Final, Copy, v2, Canva.

**Examples, all from one batch**

```
Welcome
Countdown - 5 Min
Announcement - Youth Camp 2026
Announcement - Youth Camp 2026 - Details
Giving
Giving - Love Offering
Giving - Bank Details
Sermon - Anchored Wk 3
Sermon - Anchored Wk 3 - Hebrews 6.19
Sermon - Anchored Wk 3 - Point 1 Hope Holds
Worship - Amazing Grace - Verse 1
Connect - New Here
Closing - Thanks For Coming
Background - Purple Particles Loop
```

## Photos & files (everyday files on disk)

Names that make a file easy to find in Finder or File Explorer years later, and that sort sensibly.

**Format:** `YYYY-MM-DD Subject - Type or Detail`

- The date goes first only when the file belongs to a date: photos (the date the photo was taken), dated documents (the document's own date), and screenshots or photos with a date in their original name. Logos, templates, manuals, artwork and forms get no date.
- Subject is who or what it is about: the business, event, place or product.
- Type is the kind of file (Invoice 4471, Receipt, Letter, Registration Form, Manual, Logo, Screenshot) or, for photos, what is happening in a few words.
- The AI never guesses who is in a photo. People's names only appear when they are written on the file or given in the context.

**Examples**

```
2026-09-14 Youth Camp - Campfire Worship
2026-08-03 Officeworks - Invoice 4471
2026-09-02 ProPresenter - Stage Display Screenshot
Riverside Church - Logo White
Youth Camp 2026 - Registration Form
Canon EOS R8 - User Manual
```

## Making it yours

- **Context** (the box under the folder path) applies to one batch: "Sun 12 Oct · Anchored series wk 3 · Ps Dave". The AI uses it to fill gaps, never to invent content that is not on the files.
- **Names already in the folder** are sent to the AI as taken, so a new giving slide next to last week's `Giving` becomes something like `Giving - Love Offering` rather than a second `Giving`. Any clash it still makes shows as `(2)` in the review grid, before anything is renamed.
- **Keep order** adds `01 `, `02 `… in the original order, so a deck imported into ProPresenter stays in sequence. It turns itself on when the files are numbered in sequence (`1.png`, `2.png`…). The numbers are added by the app, not the AI, and editing a name never removes its number.
- To change the convention for good (your church's own words, such as Offering instead of Giving), use *Settings → Naming prompts* in the app, or edit the defaults in `conventions.py`.
