"""Check the built app renders a loop video and swaps it in: run --loop-test on a
throwaway home folder twice and expect Version 1 then Version 2 in place, 1920×1080.
On Windows, hold the video open as ProPresenter would while playing it, and expect
the swap to be refused and the old video kept; let go, and the next run goes in.

    python scripts/smoke_loop_test.py "dist/Smart Explorer/Smart Explorer.exe"
    python scripts/smoke_loop_test.py .venv/bin/python desktop.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg


def main(cmd):
    home = Path(tempfile.mkdtemp(prefix="se-loop-"))
    out = home / "ProPresenter Loops"
    out.mkdir()
    video = out / "Smart Explorer loop test.mp4"
    state = home / ".smart-explorer" / "loop-test.json"
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), SMART_EXPLORER_LOOP_TEST_TRY="10")

    def run():
        subprocess.run(cmd + ["--loop-test", str(out)], env=env, timeout=300)
        try:
            return json.loads(state.read_text("utf-8"))["version"]
        except (OSError, ValueError, KeyError):
            return 0

    def log():
        try:
            return (home / ".smart-explorer" / "loop-test.log").read_text("utf-8")
        except OSError:
            return "(no loop-test.log)"

    if run() != 1 or not video.is_file():
        print("the first run made no video\n" + log())
        return 1
    meta = next(imageio_ffmpeg.read_frames(str(video)))
    if tuple(meta["size"]) != (1920, 1080):
        print("the video is %s, not 1920x1080" % (meta["size"],))
        return 1
    first = video.read_bytes()
    if run() != 2 or video.read_bytes() == first:
        print("the second run didn't swap in Version 2\n" + log())
        return 1
    if sys.platform == "win32":
        second = video.read_bytes()
        with open(video, "rb"):
            if run() != 2 or video.read_bytes() != second:
                print("the swap went in while the video was open\n" + log())
                return 1
        if "in use" not in log():
            print("the refused swap wasn't logged\n" + log())
            return 1
        if run() != 3:
            print("the swap didn't go in once the video was let go\n" + log())
            return 1
    left = sorted(p.name for p in out.iterdir())
    if left != [video.name]:
        print("files left in the folder: %s" % left)
        return 1
    print("loop test: rendered and swapped in\n" + log())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
