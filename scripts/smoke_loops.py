"""Check loop videos end to end: start the app with --watch on a throwaway home folder
with one Render into video row, and expect its video in the save-to folder; add a
screen and expect it rendered again. On Windows, hold the video open as ProPresenter
does while playing it: the new one must wait, then go in once it is let go.
(SMART_EXPLORER_LOOP_QUIET and _SWAP_AGAIN shorten the waits.)

    python scripts/smoke_loops.py "dist/Smart Explorer/Smart Explorer.exe"
    python scripts/smoke_loops.py .venv/bin/python desktop.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import imageio_ffmpeg
from PIL import Image


def main(cmd):
    home = Path(tempfile.mkdtemp(prefix="se-loops-"))
    src, out = home / "PreServiceLoop", home / "ProPresenter Loops"
    src.mkdir()
    out.mkdir()
    for n, colour in (("1 Welcome.png", "navy"), ("2 Cafe.png", "teal")):
        Image.new("RGB", (640, 360), colour).save(src / n)
    cfg = home / ".smart-explorer"
    cfg.mkdir()
    row = {"path": str(src), "name": "Pre-service loop", "rename": False, "render": True, "output": str(out)}
    (cfg / "config.json").write_text(json.dumps({"watch": {"enabled": True, "rows": [row], "startup_wait_min": 0}}))
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               SMART_EXPLORER_LOOP_QUIET="3", SMART_EXPLORER_LOOP_SWAP_AGAIN="3")
    video = out / "Pre-service loop.mp4"
    proc = subprocess.Popen(cmd + ["--watch"], env=env)

    def loop():
        try:
            return (json.loads((cfg / "watch" / "status.json").read_text("utf-8")).get("loops") or [{}])[0]
        except (OSError, ValueError):
            return {}

    def wait_for(what, test, seconds=180):
        for _ in range(seconds):
            if test():
                return True
            time.sleep(1)
        print("timed out waiting for %s; the loop says %s" % (what, loop()))
        try:
            print((cfg / "watch" / "watch.log").read_text("utf-8"))
        except OSError:
            pass
        return False

    def screens(n):
        return lambda: loop().get("state") == "ok" and loop().get("text", "").startswith(
            "Pre-service loop.mp4 · %d screens" % n)

    try:
        if not wait_for("the first video", screens(2)):
            return 1
        meta = next(imageio_ffmpeg.read_frames(str(video)))
        if tuple(meta["size"]) != (1920, 1080):
            print("the video is %s, not 1920x1080" % (meta["size"],))
            return 1
        Image.new("RGB", (640, 360), "maroon").save(src / "3 Youth Camp.png")
        if not wait_for("the video with the new screen", screens(3)):
            return 1
        if sys.platform == "win32":
            before = video.read_bytes()
            with open(video, "rb"):
                Image.new("RGB", (360, 640), "olive").save(src / "4 Kids.png")
                if not wait_for("the swap to wait while the video is open", lambda: loop().get("state") == "staged"):
                    return 1
                time.sleep(8)  # a few tries at the swap, all refused
                if video.read_bytes() != before or loop().get("state") != "staged":
                    print("the swap went in while the video was open: %s" % loop())
                    return 1
            if not wait_for("the swap once the video was let go", screens(4), 60):
                return 1
        left = sorted(p.name for p in out.iterdir())
        if left != [video.name]:
            print("files left in the save-to folder: %s" % left)
            return 1
        print("loop videos: rendered, rendered again, swapped in")
        return 0
    finally:
        (cfg / "watch" / "stop").write_text("stop")
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
