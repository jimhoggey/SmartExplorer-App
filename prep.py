"""Turn a file into what the model sees: JPEG images, any text layer, and facts
(size, duration, pages, photo date) the model cannot reliably read off pixels."""
import base64
import io
import re
import threading

import imageio_ffmpeg
from PIL import Image, ImageOps

try:  # iPhone photos. Optional so a missing wheel never stops slides working.
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

MAX_SIDE = 1024
PDF_MAX_SIDE = 1536  # documents carry smaller text than slides
PDF_TEXT_LIMIT = 2000
PDFIUM = threading.Lock()  # PDFium is not thread-safe: two PDFs at once can crash the process
RATIOS = [("16:9", 16 / 9), ("4:3", 4 / 3), ("3:2", 3 / 2), ("1:1", 1.0), ("4:5", 4 / 5), ("2:3", 2 / 3),
          ("3:4", 3 / 4), ("9:16", 9 / 16), ("21:9", 21 / 9), ("32:9", 32 / 9)]


def _has_alpha(img):
    return img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info


def _flatten(img):
    """RGB for JPEG. Transparent areas go mid-grey: a plain convert turns them
    black, which hides black text on a transparent lower third or prop."""
    if img.mode.startswith("I;16") or img.mode == "I":
        img = img.convert("I").point(lambda v: v / 256).convert("L")  # 16-bit would clip to white
    if not _has_alpha(img):
        return img.convert("RGB")
    img = img.convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", img.size, (128, 128, 128, 255)), img).convert("RGB")


def _jpeg_b64(img, max_side):
    img = _flatten(img)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def aspect(w, h):
    """'16:9 landscape', '9:16 portrait', '1:1 square', '32:9 ultrawide'."""
    if not w or not h:
        return ""
    r = w / h
    label, ref = min(RATIOS, key=lambda x: abs(x[1] - r))
    if abs(ref - r) / ref > 0.03:
        label = "%.2f:1" % r
    shape = "square" if abs(r - 1) < 0.03 else "ultrawide" if r > 2.1 else "landscape" if r > 1 else "portrait"
    return "%s %s" % (label, shape)


def _open(path):
    img = Image.open(path)
    img.seek(0)  # first frame of a GIF or multi-page TIFF
    return img


def _taken(img):
    """Photo date from EXIF as YYYY-MM-DD, or None."""
    try:
        exif = img.getexif()
        raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)
    except Exception:
        return None
    m = re.match(r"(\d{4}):(\d{2}):(\d{2})", str(raw or ""))
    return "-".join(m.groups()) if m and m.group(1) != "0000" else None


def image_b64(path, max_side=MAX_SIDE):
    return _jpeg_b64(ImageOps.exif_transpose(_open(path)), max_side)


def video_frames_b64(path, n=3, max_side=MAX_SIDE, with_meta=False):
    gen = imageio_ffmpeg.read_frames(path)
    meta = next(gen)
    total = max(int(meta["duration"] * meta["fps"]), 1)
    wanted = sorted({min(int(total * f), total - 1) for f in (0.1, 0.5, 0.9)[:n]})
    out, last = [], None
    try:
        for i, frame in enumerate(gen):
            last = frame
            if i in wanted:
                out.append(_jpeg_b64(Image.frombytes("RGB", meta["size"], frame), max_side))
            if i >= wanted[-1]:
                break
    finally:
        gen.close()
    if not out and last is not None:  # duration came from a longer audio track: fewer frames than expected
        out.append(_jpeg_b64(Image.frombytes("RGB", meta["size"], last), max_side))
    if not out:
        raise ValueError("No frames decoded from %s" % path)
    return (out, meta) if with_meta else out


def _pdf(path, max_side, text_limit=PDF_TEXT_LIMIT):
    import pypdfium2 as pdfium

    with PDFIUM:
        pdf = pdfium.PdfDocument(path)
        try:
            page = pdf[0]
            w, h = page.get_size()
            img = page.render(scale=max_side / max(w, h, 1)).to_pil().copy()  # own the pixels before closing
            text = ""
            if text_limit:
                tp = page.get_textpage()
                text = re.sub(r"\s+", " ", tp.get_text_range()).strip()[:text_limit]
                tp.close()
            page.close()
            return img, text, len(pdf)
        finally:
            pdf.close()


def thumb_b64(path, kind):
    if kind == "video":
        return video_frames_b64(path, 1, 240)[0]
    if kind == "pdf":
        return _jpeg_b64(_pdf(path, 240, text_limit=0)[0], 240)
    return image_b64(path, 240)


def encode(item):
    """{"images": [base64 JPEG...], "text": str, "facts": {...}} for one scanned item."""
    path, kind = item["path"], item["kind"]
    if kind == "video":
        frames, meta = video_frames_b64(path, with_meta=True)
        w, h = meta["size"]
        facts = {"size": "%dx%d" % (w, h), "aspect": aspect(w, h)}
        if meta.get("duration"):
            facts["duration"] = "%ds" % round(meta["duration"])
        return {"images": frames, "text": "", "facts": facts}
    if kind == "pdf":
        img, text, pages = _pdf(path, PDF_MAX_SIDE)
        facts = {"pages": pages, "aspect": aspect(*img.size)}
        return {"images": [_jpeg_b64(img, PDF_MAX_SIDE)], "text": text, "facts": facts}
    img = _open(path)
    taken = _taken(img)
    img = ImageOps.exif_transpose(img)
    facts = {"size": "%dx%d" % img.size, "aspect": aspect(*img.size)}
    if taken:
        facts["taken"] = taken
    if _has_alpha(img) and img.convert("RGBA").getchannel("A").getextrema()[0] < 255:
        facts["transparent"] = "yes, shown on grey"  # props and lower thirds in ProPresenter
    return {"images": [_jpeg_b64(img, MAX_SIDE)], "text": "", "facts": facts}
