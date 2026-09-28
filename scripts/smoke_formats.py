"""Release smoke test: the packaged app must read PNG, HEIC and PDF, not just start.

    python scripts/smoke_formats.py http://127.0.0.1:8765

A missing native library (libheif, pdfium) in a PyInstaller build only shows up
at runtime, as blank thumbnails and unreadable files.
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()
folder = Path(tempfile.mkdtemp())
Image.new("RGB", (64, 48), "red").save(folder / "a.png")
Image.new("RGB", (64, 48), "blue").save(folder / "b.heic", format="HEIF")
Image.new("RGB", (64, 48), "green").save(folder / "c.pdf")
req = urllib.request.Request(sys.argv[1] + "/api/scan", data=json.dumps({"paths": [str(folder)]}).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    got = {i["name"]: bool(i["thumb"]) for i in json.load(r)["items"]}
print(got)
sys.exit(0 if got == {"a.png": True, "b.heic": True, "c.pdf": True} else 1)
