"""Loop Builder: the pictures and videos in a folder rendered into one looping video
for ProPresenter, then swapped in under a fixed name. Design:
docs/superpowers/specs/2026-11-06-loop-builder-design.md.

A render is planned (each screen read; pictures prepared in a work folder), run by
the bundled ffmpeg as a child process at low priority, then staged next to the old
video under a name ProPresenter doesn't import and swapped over it in one step.
"""
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageOps, ImageSequence

import prep  # also teaches Pillow to open HEIC
import scanner

W, H, FPS = 1920, 1080, 30
STILL = 10  # seconds a picture shows, and the least an animated picture fills
FADE = 1  # seconds of each crossfade
MIN_CLIP = 2  # a shorter video is held on its last frame to this: its two crossfades must not overlap
FRAME_DEFAULT = 0.1  # seconds for an animation frame that says 0 or 10 ms, as browsers show them
ANIMATED = {"GIF", "WEBP", "PNG"}  # formats whose frames are an animation (a multi-page TIFF is not)
FIT = ("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,"
       "setsar=1,fps=%d,format=yuv420p" % (W, H, W, H, FPS))


@dataclass
class Clip:
    path: Path  # the screen in the loop folder
    kind: str  # "still", "animated" or "video"
    length: float  # seconds on screen, its crossfades included
    source: Path  # what ffmpeg reads: a prepared PNG, a frame list, or the video itself


def screens(folder):
    """The pictures and videos in a folder (not its subfolders), in File Explorer's order."""
    return [Path(it["path"]) for it in scanner.scan(folder) if it["kind"] in ("image", "video")]


def fresh(work):
    """An empty work folder."""
    work = Path(work)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    return work


def plan(paths, work, still=STILL):
    """(clips, left_out) for the screens in order. Pictures are prepared in `work`; a
    file that can't be read (half downloaded, corrupt) is left out as (path, why), and
    the rest of the loop still renders."""
    clips, left_out = [], []
    for i, path in enumerate(paths):
        path = Path(path)
        try:
            if scanner.kind(path) == "video":
                clips.append(Clip(path, "video", max(video_length(path), MIN_CLIP), path))
            else:
                clips.append(_picture(path, Path(work) / ("%03d" % i), still))
        except Exception as e:
            left_out.append((path, str(e) or type(e).__name__))
    return clips, left_out


def video_length(path):
    """Seconds, from the video's header (decoding it all only when the header has none)."""
    gen = imageio_ffmpeg.read_frames(str(path))
    try:
        meta = next(gen)
    finally:
        gen.close()
    secs = meta.get("duration") or 0
    if secs <= 0:
        secs = imageio_ffmpeg.count_frames_and_secs(str(path))[1]
    if secs <= 0:
        raise ValueError("no picture in it")
    return float(secs)


def _fit(img):
    """RGB with transparency on black, shrunk to fit 1920×1080 (ffmpeg scales it to fill)."""
    img = prep._flatten(img, background=(0, 0, 0))
    img.thumbnail((W, H), Image.LANCZOS)
    return img


def _picture(path, stem, still):
    img = Image.open(path)
    if img.format in ANIMATED and getattr(img, "is_animated", False):
        return _animated(path, img, stem, still)
    out = stem.with_suffix(".png")
    _fit(ImageOps.exif_transpose(prep._open(path))).save(out)
    return Clip(path, "still", still, out)


def _animated(path, img, stem, still):
    """An animated GIF, WebP or PNG as a list for ffmpeg's concat reader: each frame once
    as a PNG with its duration, repeated to fill `still` seconds, or played once if longer."""
    stem.mkdir(parents=True, exist_ok=True)
    frames = []
    for n, frame in enumerate(ImageSequence.Iterator(img)):
        name = "f%04d.png" % n
        _fit(frame.convert("RGBA")).save(stem / name)
        secs = (frame.info.get("duration") or 0) / 1000
        frames.append((name, secs if secs > 0.01 else FRAME_DEFAULT))
    length = max(sum(s for _, s in frames), still)
    lines, t = ["ffconcat version 1.0"], 0.0
    while t < length - 1e-6:
        for name, secs in frames:
            lines += ["file '%s'" % name, "duration %.3f" % secs]
            t += secs
            if t >= length - 1e-6:
                break
    lines.append("file '%s'" % name)  # the reader skips the last duration unless the file is listed again
    listing = stem / "frames.ffconcat"
    listing.write_text("\n".join(lines) + "\n", "utf-8")
    return Clip(path, "animated", length, listing)


def length(clips):
    """Seconds of the finished video: the clips, less one crossfade between each pair
    (the wrap into the first screen adds none)."""
    return sum(c.length for c in clips) - FADE * max(len(clips) - 1, 0)


def graph(clips):
    """(filter graph, output label). Each clip fitted to 1920×1080 at 30 fps and cut to
    its length (held on its last frame if it ends early), crossfaded into the next; the
    last crossfades into the first screen's first frame, so the loop wraps with no jump.
    One screen: just that screen."""
    # xfade needs a constant frame rate on both inputs, and setpts drops it: fps again last. tpad
    # needs it too, to know how many frames to hold, so the first frame is taken before any setpts.
    parts = ["[%d:v]%s,tpad=stop_mode=clone:stop_duration=%.3f,trim=duration=%.3f,setpts=PTS-STARTPTS,"
             "fps=%d,settb=AVTB[c%d]" % (i, FIT, c.length, c.length, FPS, i) for i, c in enumerate(clips)]
    if len(clips) == 1:
        return ";".join(parts), "[c0]"
    parts.append("[c0]split=2[v0][h];[h]trim=end_frame=1,fps=%d,tpad=stop_mode=clone:stop_duration=%g,"
                 "trim=duration=%g,fps=%d,settb=AVTB[head]" % (FPS, FADE, FADE, FPS))
    prev, offset = "v0", 0.0
    for i in range(1, len(clips)):
        offset += clips[i - 1].length - FADE
        parts.append("[%s][c%d]xfade=transition=fade:duration=%g:offset=%.3f[x%d]" % (prev, i, FADE, offset, i))
        prev = "x%d" % i
    parts.append("[%s][head]xfade=transition=fade:duration=%g:offset=%.3f[out]" % (prev, FADE, length(clips) - FADE))
    return ";".join(parts), "[out]"


def _input(c):
    if c.kind == "still":
        return ["-loop", "1", "-framerate", str(FPS), "-t", "%.3f" % c.length, "-i", str(c.source)]
    if c.kind == "animated":
        return ["-f", "concat", "-safe", "0", "-i", str(c.source)]
    return ["-i", str(c.source)]


def command(clips, out, work):
    """ffmpeg's argv to render the clips into `out`: H.264, 1920×1080, 30 fps, no sound.
    The graph goes in a file, as a long loop's command line would pass Windows' limit
    (`-/filter_complex FILE`: ffmpeg 7 and later; 8 dropped -filter_complex_script)."""
    work = Path(work)
    text, label = graph(clips)
    (work / "graph.txt").write_text(text, "utf-8")
    argv = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostdin", "-y"]
    for c in clips:
        argv += _input(c)
    return argv + ["-/filter_complex", str(work / "graph.txt"), "-map", label, "-an",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
                   "-movflags", "+faststart", "-progress", str(work / "progress.txt"), "-nostats", str(out)]


def start(argv, work):
    """Run ffmpeg as a child process at low priority (ProPresenter comes first), with its
    messages in work/ffmpeg.log. Returns the Popen."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW
    else:
        kw["preexec_fn"] = lambda: os.nice(10)
    with open(Path(work) / "ffmpeg.log", "wb") as log:
        return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log, **kw)


def progress(work, total):
    """0 to 1: how far ffmpeg has got through `total` seconds, from its progress file."""
    try:
        text = (Path(work) / "progress.txt").read_text("utf-8", "replace")
    except OSError:
        return 0.0
    done = re.findall(r"out_time_us=(\d+)", text)
    return min(1.0, int(done[-1]) / 1e6 / total) if done and total > 0 else 0.0


def tail(work, lines=20):
    """The last lines ffmpeg wrote, for the log when a render fails."""
    try:
        text = (Path(work) / "ffmpeg.log").read_text("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(text.strip().splitlines()[-lines:])


def video_path(folder, name):
    return Path(folder) / (name + ".mp4")


def part_path(folder, name):
    return Path(folder) / (name + ".mp4.part")


def stage(video, folder, name):
    """Copy a finished video next to the old one, under a name ProPresenter doesn't import."""
    part = part_path(folder, name)
    shutil.copyfile(video, part)
    return part


def put(folder, name):
    """Swap the staged video in over the old one in one step, so ProPresenter never sees a
    half-written file. Raises PermissionError while something (ProPresenter playing it)
    holds the old one open on Windows; the staged copy stays, so a later try only swaps."""
    os.replace(part_path(folder, name), video_path(folder, name))
    return video_path(folder, name)


def clear_stage(folder, name):
    """Delete a staged copy left by a crash, a switch-off or a swap given up on."""
    try:
        part_path(folder, name).unlink()
    except FileNotFoundError:
        pass
