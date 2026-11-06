"""The rig test for Loop Builder (spec: Rig test). `Smart Explorer --loop-test FOLDER`
renders a short video of coloured screens reading "Loop test, Version N" and swaps it
into FOLDER as "Smart Explorer loop test.mp4", exactly as a loop will be swapped in.
Each run that gets its video in is the next version. It says how it went in a
notification and in loop-test.log, as the app has no window then.

Run it twice with ProPresenter's smart playlist pointed at FOLDER: does the playlist
keep the video and play Version 2? Then once while the loop plays: is the swap refused
until it stops?
"""
import json
import os
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

import config
import loops
import notify

NAME = "Smart Explorer loop test"
COLOURS = [(79, 70, 229), (6, 118, 71), (180, 83, 9)]
SECONDS = 5  # each screen: a short video renders quickly
TRY_EVERY = 5  # seconds between tries at a refused swap


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without FreeType: small, but still readable
        return ImageFont.load_default()


def _screen(path, colour, version, n):
    img = Image.new("RGB", (loops.W, loops.H), colour)
    draw = ImageDraw.Draw(img)
    for text, size, y in (("Loop test", 90, 330), ("Version %d" % version, 200, 470),
                          ("Screen %d of %d" % (n, len(COLOURS)), 60, 760)):
        draw.text((loops.W // 2, y), text, font=_font(size), fill="white", anchor="mm")
    img.save(path)
    return path


def _log(line):
    try:
        with open(config.CONFIG_DIR / "loop-test.log", "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


def main(folder, say=notify.notify, sleep=time.sleep, clock=time.monotonic, try_for=None):
    """Returns 0 when the new version went in, else 1."""
    folder = config.clean_folder(folder)
    if not folder or not os.path.isdir(folder):
        return _done(say, 1, "Loop test: can't find the folder %s." % (folder or "(none given)"))
    try_for = int(os.environ.get("SMART_EXPLORER_LOOP_TEST_TRY", 120)) if try_for is None else try_for
    state = config.CONFIG_DIR / "loop-test.json"
    try:
        version = json.loads(state.read_text("utf-8")).get("version", 0) + 1
    except (OSError, ValueError):
        version = 1
    work = loops.fresh(config.CONFIG_DIR / "loops" / "test")
    shots = [_screen(work / ("screen%d.png" % n), c, version, n) for n, c in enumerate(COLOURS, 1)]
    clips, _ = loops.plan(shots, work, still=SECONDS)
    out = work / "render.mp4"
    started = clock()
    proc = loops.start(loops.command(clips, out, work), work)
    if proc.wait() != 0:
        _log("version %d: render failed\n%s" % (version, loops.tail(work)))
        return _done(say, 1, "Loop test: the render failed. The details are in loop-test.log.")
    took = clock() - started
    loops.clear_stage(folder, NAME)
    loops.stage(out, folder, NAME)
    first_try = clock()
    while True:
        try:
            loops.put(folder, NAME)
            break
        except PermissionError:
            if clock() - first_try >= try_for:
                loops.clear_stage(folder, NAME)
                _log("version %d: rendered in %.1f s; in use, refused for %d s" % (version, took, try_for))
                return _done(say, 1, "Loop test: Version %d couldn't go in, %s.mp4 is in use. Stop the loop in "
                                     "ProPresenter and run the test again." % (version, NAME))
            sleep(TRY_EVERY)
    waited = clock() - first_try
    config.write_json(state, {"version": version})
    _log("version %d: rendered in %.1f s, in place%s" % (
        version, took, " after %d s in use" % waited if waited >= 1 else ""))
    return _done(say, 0, "Loop test: Version %d is in place (rendered in %d s). Check ProPresenter plays it."
                 % (version, max(1, round(took))))


def _done(say, code, text):
    _log(text)
    say(text)
    return code
