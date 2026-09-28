import base64
import io

import pytest
from PIL import Image

import prep


def _decode(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def write_pdf(path, pages):
    """A real (tiny) PDF with a text layer, one page per string."""
    n = len(pages)
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % (4 + 2 * i) for i in range(n)), n),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(pages):
        stream = "BT /F1 28 Tf 72 760 Td (%s) Tj ET" % text
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R /Resources << /Font << /F1 3 0 R >> >> >>" % (5 + 2 * i))
        objs.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (i, o)).encode()
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    out += b"".join(("%010d 00000 n \n" % off).encode() for off in offsets)
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()
    path.write_bytes(out)
    return str(path)


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "big.png"
    Image.new("RGBA", (2000, 1000), (255, 0, 0, 255)).save(p)
    return str(p)


@pytest.fixture
def mp4(tmp_path):
    import imageio_ffmpeg

    try:
        imageio_ffmpeg.get_ffmpeg_exe()
    except RuntimeError:
        pytest.skip("ffmpeg unavailable")
    p = tmp_path / "clip.mp4"
    w = imageio_ffmpeg.write_frames(str(p), (64, 64), fps=10)
    w.send(None)
    for i in range(10):
        w.send(bytes([i * 20]) * (64 * 64 * 3))
    w.close()
    return str(p)


@pytest.fixture
def pdf(tmp_path):
    return write_pdf(tmp_path / "invoice.pdf", ["TAX INVOICE 4471", "Page two"])


def test_image_b64(png):
    img = _decode(prep.image_b64(png))
    assert img.format == "JPEG"
    assert img.width <= 1024 and img.height <= 512


def test_video_frames_b64(mp4):
    frames = prep.video_frames_b64(mp4)
    assert len(frames) == 3
    assert all(_decode(f).format == "JPEG" for f in frames)


def test_thumb_b64(png, mp4, pdf):
    assert _decode(prep.thumb_b64(png, "image")).width <= 240
    assert _decode(prep.thumb_b64(mp4, "video")).width <= 240
    assert max(_decode(prep.thumb_b64(pdf, "pdf")).size) <= 240


def test_encode(png, mp4):
    e = prep.encode({"path": png, "kind": "image"})
    assert len(e["images"]) == 1 and e["text"] == ""
    assert e["facts"] == {"size": "2000x1000", "aspect": "2.00:1 landscape"}
    v = prep.encode({"path": mp4, "kind": "video"})
    assert len(v["images"]) == 3 and v["facts"]["duration"] == "1s" and v["facts"]["aspect"] == "1:1 square"


def test_encode_pdf_renders_first_page_and_reads_text(pdf):
    e = prep.encode({"path": pdf, "kind": "pdf"})
    assert len(e["images"]) == 1 and max(_decode(e["images"][0]).size) == prep.PDF_MAX_SIDE
    assert "TAX INVOICE 4471" in e["text"] and "Page two" not in e["text"]
    assert e["facts"]["pages"] == 2 and "portrait" in e["facts"]["aspect"]


def test_encode_photo_date_and_orientation(tmp_path):
    p = tmp_path / "IMG_1234.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways; viewers rotate 90 degrees clockwise
    exif.get_ifd(0x8769)[36867] = "2026:09:14 10:31:05"
    Image.new("RGB", (400, 300), "red").save(p, exif=exif.tobytes())
    e = prep.encode({"path": str(p), "kind": "image"})
    assert e["facts"] == {"size": "300x400", "aspect": "3:4 portrait", "taken": "2026-09-14"}
    assert _decode(e["images"][0]).size == (300, 400)


def test_encode_heic(tmp_path):
    pytest.importorskip("pillow_heif")
    p = tmp_path / "IMG_0001.HEIC"
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = "2025:12:25 09:00:00"
    Image.new("RGB", (640, 480), (30, 120, 200)).save(p, format="HEIF", exif=exif.tobytes())
    e = prep.encode({"path": str(p), "kind": "image"})
    assert e["facts"] == {"size": "640x480", "aspect": "4:3 landscape", "taken": "2025-12-25"}
    assert _decode(prep.thumb_b64(str(p), "image")).width == 240


def test_aspect():
    assert prep.aspect(1920, 1080) == "16:9 landscape"
    assert prep.aspect(1080, 1920) == "9:16 portrait"
    assert prep.aspect(1080, 1080) == "1:1 square"
    assert prep.aspect(3840, 1080) == "32:9 ultrawide"
    assert prep.aspect(0, 10) == ""


def test_transparent_png_keeps_dark_text_visible(tmp_path):
    """A plain RGB convert turns transparency black, so black text on a
    transparent lower third vanished before the model ever saw it."""
    p = tmp_path / "lower third.png"
    img = Image.new("RGBA", (400, 100), (0, 0, 0, 0))
    img.paste((0, 0, 0, 255), (40, 40, 360, 60))  # a black bar standing in for text
    img.save(p)
    e = prep.encode({"path": str(p), "kind": "image"})
    seen = _decode(e["images"][0]).convert("L")
    assert seen.getpixel((5, 5)) > 100 and seen.getpixel((200, 50)) < 30
    assert e["facts"]["transparent"].startswith("yes")
    solid = tmp_path / "solid.png"
    Image.new("RGBA", (40, 20), (9, 9, 9, 255)).save(solid)
    assert "transparent" not in prep.encode({"path": str(solid), "kind": "image"})["facts"]


def test_16bit_grey_png_is_not_white(tmp_path):
    p = tmp_path / "grey16.png"
    Image.new("I;16", (40, 20), 32768).save(p)  # 50% grey in 16 bits
    seen = _decode(prep.encode({"path": str(p), "kind": "image"})["images"][0]).convert("L")
    assert 100 < seen.getpixel((10, 10)) < 160


def test_colour_key_transparency_gets_grey(tmp_path):
    p = tmp_path / "keyed.png"
    img = Image.new("RGB", (40, 20), (0, 0, 0))
    img.paste((255, 255, 255), (0, 0, 20, 20))
    img.save(p, transparency=(0, 0, 0))  # black means transparent
    e = prep.encode({"path": str(p), "kind": "image"})
    seen = _decode(e["images"][0]).convert("L")
    assert 100 < seen.getpixel((30, 10)) < 160 and seen.getpixel((5, 10)) > 240
    assert e["facts"]["transparent"].startswith("yes")


def test_short_video_with_long_audio_uses_last_frame(monkeypatch):
    """ffmpeg reports the container's duration, which a long audio track can
    stretch far past the last video frame."""
    def frames(path):
        yield {"size": (8, 8), "fps": 10.0, "duration": 60.0}
        for i in range(5):  # half a second of video
            yield bytes([i * 40]) * (8 * 8 * 3)

    monkeypatch.setattr(prep.imageio_ffmpeg, "read_frames", frames)
    assert len(prep.video_frames_b64("clip.mp4")) == 1


def test_many_pdfs_in_parallel_do_not_crash(tmp_path):
    """PDFium is not thread-safe; without the lock this segfaults the process,
    so it runs in a subprocess to fail cleanly instead of killing pytest."""
    import subprocess
    import sys
    from pathlib import Path

    for i in range(12):
        write_pdf(tmp_path / ("d%02d.pdf" % i), ["Doc %d" % i])
    code = (
        "import sys; from concurrent.futures import ThreadPoolExecutor; from pathlib import Path\n"
        "sys.path.insert(0, %r); import prep\n"
        "files = sorted(Path(%r).glob('*.pdf')) * 4\n"
        "with ThreadPoolExecutor(8) as ex:\n"
        "    assert all(ex.map(lambda p: prep.thumb_b64(str(p), 'pdf'), files))\n"
    ) % (str(Path(prep.__file__).parent), str(tmp_path))
    assert subprocess.run([sys.executable, "-c", code], timeout=120).returncode == 0
