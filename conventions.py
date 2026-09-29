"""The naming conventions the AI follows, one per profile (naming style).

Each profile has:
  label        shown in the app
  description  when to use it, shown in the app
  categories   the fixed words names start with; shared by both steps
  reader       what the vision step should look for in each file (stage 1)
  rules        the convention the naming step applies to the whole batch (stage 2);
               {categories} is replaced with the list above

These are the defaults. categories, reader and rules can also be changed in the
app (Settings, Naming prompts); those edits are saved in the config file and
applied on top of the defaults here. For one batch only, type it in the app's
context box.
"""
import config

DEFAULT_PROFILE = "propresenter"
FIELDS = ("categories", "reader", "rules")  # the parts that can be edited in the app

PROFILES = {
    "propresenter": {
        "label": "ProPresenter",
        "description": "For slides, backgrounds and videos going into ProPresenter. Names start with what each file is for (Giving, Sermon, Worship and so on), so they group together and are easy to find in the media bin.",
        "categories": "Welcome (welcome and pre-service slides) · Closing (end of service: thanks for coming, see you next week, have a great week) · Countdown (countdown timers and videos) · Announcement (events, notices, registrations, promos) · Giving (offering, tithes, bank details, give online) · Sermon (series art, sermon title, points, quotes, questions) · Scripture (Bible verses that are not part of a sermon set) · Worship (song lyrics or song title slides; Subject is the song title) · Prayer · Communion · Baptism · Connect (new here, next steps, connect cards, sign-up QR codes) · Kids · Youth · Background (stills and motion loops with no meaningful text; Subject describes the look) · Lower Third (name and title straps, usually on a transparent background) · Bumper (intro, outro and transition videos) · Social (socials, follow us) · Other",
        "reader": """These files are slides, graphics and videos for church services, run in ProPresenter.
- Read every piece of text exactly as written. Do not correct, complete or invent text.
- Song lyrics: if you recognise the song, put its title in notes. If you are not sure, say so.
- Bible verses: put the reference in subject (e.g. Hebrews 6:19).
- Put the most specific name shown in subject: Love Offering or Building Fund rather than just Giving, the event's name rather than just Announcement.
- Say whether the file shows only a headline or the full details (dates, prices, bank details, links, QR code).
- Videos: say whether it looks like a countdown, a motion background or loop, or a promo.
- Describe the look in visual: colours, imagery, style. That is what tells matching designs and text-free backgrounds apart.""",
        "rules": """These files will be imported into ProPresenter for church services. ProPresenter shows each file name under its thumbnail in the media bin, where long names get cut off, and finds media by searching names. So names must be short, front-loaded, and the same from week to week.

Format: Category - Subject - Detail
- Category: exactly one from the list below. It always comes first, so files group together and a search for "Giving" finds every giving slide.
- Subject: the specific thing: event name, sermon series and week, song title, Bible reference, or the slide's own short heading (Closing - Thanks For Coming). Leave it out only when it would just repeat the category (Giving, not Giving - Giving).
- Detail: only for files that would otherwise share a name with another file in this batch. A file with no look-alike gets no Detail: the only giving slide is just Giving.

Telling look-alikes apart:
- Use the words that differ between them, taken from the files themselves: a second giving slide that says Love Offering is Giving - Love Offering, next to plain Giving.
- Only when the wording is the same, say what else differs: Bank Details or Details (dates, prices, links shown), QR, Portrait, Loop, Verse 1.
- The plainest file of a set keeps the name without a Detail.

Categories:
{categories}

Style:
- Title Case. Single spaces between words, " - " between parts. Keep acronyms as written (QR, BSB, NIV).
- Aim for 40 characters or fewer, never more than 60. Drop filler words (the, our, join us, presents, welcome to).
- Bible references use a full stop, not a colon: John 3.16, Romans 8.28-30, Psalm 23. Times too: 10.30am.
- Dates are day then short month: Sun 19 Oct, 3-5 Oct. Add a year only when it is part of an event's name (Youth Camp 2026).
- Sermon slides: Sermon - Series Wk N for the series slide, then Sermon - Series Wk N - Part for the rest (Sermon - Anchored Wk 3 - Point 1 Hope Holds). Verses, quotes and points that share a sermon's design belong to that sermon (Sermon - Anchored Wk 3 - Hebrews 6.19), not to Scripture.
- Song lyrics: Worship - Song Title - Section, using ProPresenter's section names: Verse 1, Pre-Chorus, Chorus, Bridge, Tag, Ending. Name the song only when the reader was confident; otherwise use the first line as the Subject.
- Countdowns: give the length, from the timer on screen or the video duration (Countdown - 5 Min).
- The same design in several sizes: add Portrait, Square or Ultrawide from the aspect ratio. The 16:9 version gets no size.
- Never put these in a name: file extensions, sequence numbers (the app adds numbers when order matters), the words Slide, Image, Graphic, Final, Copy or v2, Canva, or an export date.

Examples, all from one batch:
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
Background - Purple Particles Loop""",
    },
    "general": {
        "label": "Photos & files",
        "description": "For everyday files on your computer: photos, screenshots, receipts, invoices and letters. Names start with the date, so a folder sorts by date.",
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


def resolve(profile):
    return profile if profile in PROFILES else DEFAULT_PROFILE


def only_edits(profile, fields):
    """The fields that change the default: non-empty text that differs from it.
    An emptied field means "use the default"."""
    base = PROFILES[resolve(profile)]
    return {k: v for k, v in fields.items()
            if k in FIELDS and isinstance(v, str) and v.strip() and v.strip() != base[k].strip()}


def edits(profile):
    """The edits saved from the app for a profile."""
    saved = config.load().get("prompt_edits")
    got = saved.get(resolve(profile)) if isinstance(saved, dict) else None
    return only_edits(profile, got) if isinstance(got, dict) else {}


def merged(profile, fields):
    """The saved edits with these fields applied: a field given empty goes back to
    the default, a field not given keeps its saved edit."""
    out = edits(profile)
    for k, v in fields.items():
        if k in FIELDS and isinstance(v, str):
            out.pop(k, None)
    out.update(only_edits(profile, fields))
    return out


def get(profile, draft=None):
    """A profile as the AI gets it: the defaults, with the saved edits (and, for a
    preview, the draft ones) on top, and the categories put into the rules."""
    p = dict(PROFILES[resolve(profile)], **(edits(profile) if draft is None else merged(profile, draft)))
    return dict(p, rules=p["rules"].replace("{categories}", p["categories"]))
