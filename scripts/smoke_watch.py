"""Check background renaming end to end: start the app with --watch on a throwaway
home folder (no key: SMART_EXPLORER_MOCK names files "Slide N"), drop two numbered
images into the watched folder, and wait for them to be renamed.

    python scripts/smoke_watch.py "dist/Smart Explorer/Smart Explorer.exe"
    python scripts/smoke_watch.py .venv/bin/python desktop.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image


def main(cmd):
    home = Path(tempfile.mkdtemp(prefix="se-watch-"))
    folder = home / "Sunday Media"
    folder.mkdir()
    cfg = home / ".smart-explorer"
    cfg.mkdir()
    (cfg / "config.json").write_text(json.dumps({"watch": {"enabled": True, "folder": str(folder), "startup_wait_min": 0}}))
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), SMART_EXPLORER_MOCK="1")
    proc = subprocess.Popen(cmd + ["--watch"], env=env)
    status = cfg / "watch" / "status.json"
    try:
        # Drop the files only once the watcher has looked at the (empty) folder: a slow
        # start (Windows) must not see them first and record them as already there.
        for _ in range(60):
            time.sleep(1)
            try:
                if json.loads(status.read_text("utf-8")).get("state") == "watching":
                    break
            except (OSError, ValueError):
                pass
        else:
            print("the watcher never started watching")
            return 1
        for n, color in (("1.png", "red"), ("2.png", "blue")):
            Image.new("RGB", (64 + len(color), 36), color).save(folder / n)
        for _ in range(60):
            time.sleep(3)
            names = sorted(p.name for p in folder.iterdir())
            if names == ["01 Slide 1.png", "02 Slide 2.png"]:
                print("renamed:", names)
                (cfg / "watch" / "stop").write_text("stop")
                proc.wait(timeout=30)
                return 0
        print("not renamed:", sorted(p.name for p in folder.iterdir()))
        for name in ("status.json", "watch.log"):
            p = cfg / "watch" / name
            print(p.read_text("utf-8") if p.exists() else "%s missing" % name)
        return 1
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
