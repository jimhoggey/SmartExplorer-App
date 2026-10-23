"""Draw the Smart Explorer app icon and export .ico / .icns / .png / favicon.

A file explorer's folder, with the files peeking out and an AI sparkle on the
front, on an indigo panel (the app's accent colour). One list of shapes feeds both
the bitmaps and the SVG favicon, which the window also uses as its header mark,
so every place shows the same icon. At small sizes the details are dropped so the
folder stays readable in the Windows taskbar.

Run: python scripts/make_icon.py
"""
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
S = 4  # supersample

PANEL_TOP, PANEL_BOT = (109, 102, 245), (67, 56, 202)  # indigo, as the app's accent
BACK, PAPER, FRONT, SPARK = (232, 145, 20), (255, 248, 230), (255, 197, 61), (67, 56, 202)


def sparkle(cx, cy, r, steps=72, p=2.6):
    """A four-point star with curved sides (a stretched astroid)."""
    out = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        out.append((cx + r * math.copysign(abs(c) ** p, c), cy + r * math.copysign(abs(s) ** p, s)))
    return out


def shapes(px):
    """The icon's shapes in a 1024 box, back to front, with fewer details when small."""
    out = [("rect", (164, 236, 452, 420), 48, BACK),  # the folder's tab, reaching into the back: no notch
           ("rect", (164, 300, 860, 800), 60, BACK)]  # its back
    if px >= 48:
        out.append(("rect", (214, 296, 810, 520), 28, PAPER))  # files peeking out
    out.append(("rect", (164, 400, 860, 800), 60, FRONT))  # the front
    if px > 24:
        out.append(("poly", sparkle(500, 612, 150), None, SPARK))
    if px >= 48:
        out.append(("poly", sparkle(664, 500, 52), None, SPARK))
    return out


def draw(px):
    n = 1024 * S
    grad = Image.new("RGB", (1, n))
    for y in range(n):
        t = y / (n - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(PANEL_TOP, PANEL_BOT)))
    img = grad.resize((n, n))
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n - 1, n - 1), radius=230 * S, fill=255)
    icon = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    icon.paste(img, (0, 0), mask)
    d = ImageDraw.Draw(icon)
    for kind, geo, radius, colour in shapes(px):
        if kind == "rect":
            d.rounded_rectangle(tuple(v * S for v in geo), radius=radius * S, fill=colour)
        else:
            d.polygon([(x * S, y * S) for x, y in geo], fill=colour)
    return icon.resize((px, px), Image.LANCZOS)


def svg():
    hexc = lambda c: "#%02x%02x%02x" % c
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">',
             '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient></defs>'
             % (hexc(PANEL_TOP), hexc(PANEL_BOT)),
             '<rect width="1024" height="1024" rx="230" fill="url(#g)"/>']
    for kind, geo, radius, colour in shapes(1024):
        if kind == "rect":
            x0, y0, x1, y1 = geo
            parts.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="%s"/>'
                         % (x0, y0, x1 - x0, y1 - y0, radius, hexc(colour)))
        else:
            points = " ".join("%.1f,%.1f" % xy for xy in geo)
            parts.append('<polygon points="%s" fill="%s"/>' % (points, hexc(colour)))
    return "".join(parts) + "</svg>\n"


def main():
    ASSETS.mkdir(exist_ok=True)
    draw(1024).save(ASSETS / "icon.png")

    # Windows .ico. Pillow drops requested sizes larger than the base image, so save
    # from the biggest frame and supply every other size via append_images.
    px = (16, 24, 32, 48, 64, 128, 256)
    layers = {p: draw(p) for p in px}
    layers[256].save(ASSETS / "icon.ico", format="ICO", sizes=[(p, p) for p in px],
                     append_images=[layers[p] for p in px if p != 256])

    # macOS .icns via iconutil (macOS only; the committed file is reused on CI).
    if sys.platform == "darwin":
        iconset = ASSETS / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for base in (16, 32, 128, 256, 512):
            draw(base).save(iconset / ("icon_%dx%d.png" % (base, base)))
            draw(base * 2).save(iconset / ("icon_%dx%d@2x.png" % (base, base)))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ASSETS / "icon.icns")], check=True)

    (ROOT / "static" / "icon.svg").write_text(svg(), encoding="utf-8")
    print("wrote", ASSETS / "icon.png", ASSETS / "icon.ico", ROOT / "static" / "icon.svg",
          ASSETS / "icon.icns" if sys.platform == "darwin" else "")


if __name__ == "__main__":
    main()
