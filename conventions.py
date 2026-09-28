"""The naming conventions the AI follows, one per profile.

This is the file to edit to change how files get named. Each profile has:
  label       shown in the UI
  categories  the fixed words names start with; shared by both steps
  reader      what the vision step should look for in each file (stage 1)
  rules       the convention the naming step applies to the whole batch (stage 2);
              {categories} is replaced with the list above

Per-church vocabulary does not belong here: put it in Settings > House rules,
which is sent with every batch and overrides these rules.
"""

DEFAULT_PROFILE = "propresenter"

PROFILES = {
    "propresenter": {
        "label": "ProPresenter",
        "categories": "Welcome (welcome, pre-service and holding slides) · Countdown (countdown timers and videos) · Announcement (events, notices, registrations, promos) · Giving (offering, tithes, bank details, give online) · Sermon (series art, sermon title, points, quotes, questions) · Scripture (Bible verses that are not part of a sermon set) · Worship (song lyrics or song title slides; Subject is the song title) · Prayer · Communion · Baptism · Connect (new here, next steps, connect cards, sign-up QR codes) · Kids · Youth · Background (stills and motion loops with no meaningful text; Detail describes the look) · Lower Third (name and title straps, usually on a transparent background) · Bumper (intro, outro and transition videos) · Social (socials, follow us) · Other",
        "reader": """These files are slides, graphics and videos for church services, run in ProPresenter.
- Read every piece of text exactly as written. Do not correct, complete or invent text.
- Song lyrics: if you recognise the song, put its title in notes. If you are not sure, say so.
- Bible verses: put the reference in subject (e.g. Hebrews 6:19).
- Say whether the file shows only a headline or the full details (dates, prices, bank details, links, QR code).
- Videos: say whether it looks like a countdown, a motion background or loop, or a promo.
- Describe the look in visual: colours, imagery, style. That is what tells matching designs and text-free backgrounds apart.""",
        "rules": """These files will be imported into ProPresenter for church services. ProPresenter shows each file name under its thumbnail in the media bin, where long names get cut off, and finds media by searching names. So names must be short, front-loaded, and the same from week to week.

Format: Category - Subject - Detail
- Category: exactly one from the list below. It always comes first, so files group together and a search for "Giving" finds every giving slide.
- Subject: the specific thing: event name, sermon series and week, song title, Bible reference. Leave it out when the category already says it all (Giving - Bank Details).
- Detail: only what tells this file apart from similar files in the batch: Title (headline only), Details (full information), QR, Point 1 Hope Holds, Verse 1, Chorus, Loop, Portrait, Sun 19 Oct. Leave it out if nothing needs telling apart.

Categories:
{categories}

Style:
- Title Case. Single spaces between words, " - " between parts. Keep acronyms as written (QR, BSB, NIV).
- Aim for 40 characters or fewer, never more than 60. Drop filler words (the, our, join us, presents, welcome to).
- Bible references use a full stop, not a colon: John 3.16, Romans 8.28-30, Psalm 23. Times too: 10.30am.
- Dates are day then short month: Sun 19 Oct, 3-5 Oct. Add a year only when it is part of an event's name (Youth Camp 2026).
- Sermon slides: Sermon - Series Wk N - Part (Sermon - Anchored Wk 3 - Title). Verses, quotes and points that share a sermon's design belong to that sermon (Sermon - Anchored Wk 3 - Hebrews 6.19), not to Scripture.
- Song lyrics: Worship - Song Title - Section, using ProPresenter's section names: Verse 1, Pre-Chorus, Chorus, Bridge, Tag, Ending. Name the song only when the reader was confident; otherwise use the first line as the Subject.
- Countdowns: give the length, from the timer on screen or the video duration (Countdown - 5 Min).
- The same design in several sizes: add Portrait, Square or Ultrawide from the aspect ratio. The 16:9 version gets no size.
- Never put these in a name: file extensions, sequence numbers (the app adds numbers when order matters), the words Slide, Image, Graphic, Final, Copy or v2, Canva, or an export date.

Examples:
Welcome - Welcome Home
Countdown - 5 Min
Announcement - Youth Camp 2026 - Title
Announcement - Youth Camp 2026 - Details
Giving - Title
Giving - Bank Details
Sermon - Anchored Wk 3 - Title
Sermon - Anchored Wk 3 - Hebrews 6.19
Sermon - Anchored Wk 3 - Point 1 Hope Holds
Worship - Amazing Grace - Verse 1
Connect - New Here QR
Background - Purple Particles Loop""",
    },
    "general": {
        "label": "General",
        "categories": "Photo · Screenshot · Invoice · Receipt · Statement · Letter · Form · Ticket · Certificate · Report · Minutes · Manual · Flyer · Poster · Logo · Artwork · Document · Other",
        "reader": """These are everyday files on a computer: photos, screenshots, scanned or downloaded documents, flyers and artwork.
- Read the important text exactly as written: titles, organisation and business names, document numbers, dates, totals.
- Documents: say what kind it is (invoice, receipt, statement, letter, form, ticket, certificate, report, minutes, manual, flyer, poster).
- Photos: describe the scene and the occasion in a few words. Never guess who a person is; use names only when they are written on the file.
- Screenshots: say which app or website is shown and what it shows.
- Put the most relevant date shown on the file in date (the document date, not a due date or print date).""",
        "rules": """These are everyday files on a computer. Names should make each file easy to find in Finder or File Explorer years from now, and sort sensibly by name.

Format: YYYY-MM-DD Subject - Type or Detail
- Date first, as YYYY-MM-DD, only when the file belongs to a date: photos (use the taken date from facts), dated documents such as invoices, receipts, statements, letters, tickets and minutes (use the document's own date), and screenshots or photos whose original name contains a date (IMG_20260914_103105, Screenshot 2026-09-14 at 10.31.05). Timeless files get no date: logos, templates, manuals, artwork, forms.
- Subject: who or what the file is about: the business or organisation, the event, the place or the product (Officeworks, Youth Camp 2026, Riverside Church, Canon EOS R8).
- Type or Detail: the kind of file from this list, with a number or qualifier where useful (Invoice 4471, Registration Form), or, for photos, what is happening in a few words (Campfire Worship, Group Photo, Stage Setup):
{categories}

Style:
- Title Case. Single spaces between words, " - " between parts. Keep acronyms and model numbers as written.
- Aim for 50 characters or fewer, never more than 70.
- Use a full stop instead of a colon in times and references (10.30am, John 3.16).
- Never guess who is in a photo. Use people's names only when they are written on the file or given in the context.
- Never put these in a name: file extensions, sequence numbers (the app adds numbers when order matters), the words Copy, Final, v2, Scan, Image or Untitled, camera or phone file numbers (IMG_1234), or download junk such as (1).

Examples:
2026-09-14 Youth Camp - Campfire Worship
2026-09-14 Youth Camp - Group Photo
2026-08-03 Officeworks - Invoice 4471
2026-09-02 ProPresenter - Stage Display Screenshot
Riverside Church - Logo White
Youth Camp 2026 - Registration Form
Canon EOS R8 - User Manual""",
    },
}


def get(profile):
    p = PROFILES.get(profile) or PROFILES[DEFAULT_PROFILE]
    return dict(p, rules=p["rules"].replace("{categories}", p["categories"]))
