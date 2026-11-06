import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import pytest
from PIL import Image, ImageChops, ImageStat

import loops

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def make_video(path, secs, size="320x180"):
    """A test-pattern MP4 with a sound track, made by the bundled ffmpeg."""
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=%s:rate=25:duration=%g" % (size, secs),
                    "-f", "lavfi", "-i", "sine=duration=%g" % secs, "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def make_gif(path, frames, ms):
    imgs = [Image.new("RGB", (200, 100), (40 * i % 255, 80, 160)) for i in range(frames)]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0)
    return path


def clip(secs, kind="still"):
    return loops.Clip(Path("x.png"), kind, secs, Path("x.png"))


def test_screens_are_pictures_and_videos_in_explorer_order(tmp_path):
    for name in ("10 Youth.png", "2 Cafe.jpg", "notes.pdf", "readme.txt", ".hidden.png", "Farewell.mp4"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "1.png").write_bytes(b"x")
    assert [p.name for p in loops.screens(tmp_path)] == ["2 Cafe.jpg", "10 Youth.png", "Farewell.mp4"]


def test_a_picture_is_a_still_on_black_that_fits_the_frame(tmp_path):
    src = tmp_path / "portrait.png"
    img = Image.new("RGBA", (1200, 2400), (255, 255, 255, 255))
    img.paste((0, 0, 0, 0), (0, 0, 1200, 600))  # transparent top quarter
    img.save(src)
    clips, left_out = loops.plan([src], loops.fresh(tmp_path / "work"))
    assert left_out == []
    (c,) = clips
    assert (c.kind, c.length) == ("still", loops.STILL)
    out = Image.open(c.source)
    assert out.mode == "RGB" and out.width <= 1920 and out.height <= 1080
    assert out.getpixel((out.width // 2, 5)) == (0, 0, 0)  # transparency shows as black
    assert out.getpixel((out.width // 2, out.height - 5)) == (255, 255, 255)


def test_a_sideways_photo_is_turned_the_right_way_up(tmp_path):
    src = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways: shown turned 90° clockwise
    Image.new("RGB", (400, 200), (10, 120, 30)).save(src, exif=exif.tobytes())
    (c,), _ = loops.plan([src], loops.fresh(tmp_path / "work"))
    assert Image.open(c.source).size == (200, 400)


def test_a_short_animation_repeats_to_fill_its_ten_seconds(tmp_path):
    src = make_gif(tmp_path / "spin.gif", frames=3, ms=200)
    (c,), _ = loops.plan([src], loops.fresh(tmp_path / "work"))
    assert (c.kind, c.length) == ("animated", loops.STILL)
    lines = c.source.read_text("utf-8").splitlines()
    durations = [float(line.split()[1]) for line in lines if line.startswith("duration")]
    assert sum(durations) == pytest.approx(10.0, abs=0.21)
    assert lines[-1].startswith("file ") and lines[-2].startswith("duration")  # last frame listed again


def test_a_long_animation_plays_once_at_its_own_length(tmp_path):
    src = make_gif(tmp_path / "long.gif", frames=60, ms=250)
    (c,), _ = loops.plan([src], loops.fresh(tmp_path / "work"))
    assert c.length == pytest.approx(15.0)


def test_videos_play_at_full_length_and_a_short_one_is_held_to_two_seconds(tmp_path):
    short = make_video(tmp_path / "blip.mp4", 1)
    full = make_video(tmp_path / "farewell.mp4", 3)
    (a, b), _ = loops.plan([short, full], loops.fresh(tmp_path / "work"))
    assert (a.kind, a.length) == ("video", loops.MIN_CLIP)
    assert b.length == pytest.approx(3.0, abs=0.1)


def test_a_file_that_cant_be_read_is_left_out_and_the_rest_kept(tmp_path):
    good = tmp_path / "1.png"
    Image.new("RGB", (100, 100)).save(good)
    broken = tmp_path / "2.png"
    broken.write_bytes(b"not a picture")
    half = tmp_path / "3.mp4"
    half.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    clips, left_out = loops.plan([good, broken, half], loops.fresh(tmp_path / "work"))
    assert [c.path for c in clips] == [good]
    assert [p for p, _ in left_out] == [broken, half]
    assert all(why for _, why in left_out)


def test_crossfades_overlap_the_clips_and_the_end_wraps_into_the_first(tmp_path):
    clips = [clip(10), clip(10), clip(3, "video")]
    assert loops.length(clips) == 21
    text, label = loops.graph(clips)
    assert label == "[out]"
    assert "[v0][c1]xfade=transition=fade:duration=1:offset=9.000[x1]" in text
    assert "[x1][c2]xfade=transition=fade:duration=1:offset=18.000[x2]" in text
    assert "[x2][head]xfade=transition=fade:duration=1:offset=20.000[out]" in text


def test_one_screen_is_just_that_screen(tmp_path):
    text, label = loops.graph([clip(10)])
    assert label == "[c0]" and "xfade" not in text
    assert loops.length([clip(10)]) == 10


def test_the_command_has_no_sound_and_keeps_the_graph_in_a_file(tmp_path):
    argv = loops.command([clip(10), clip(10)], tmp_path / "out.mp4", tmp_path)
    assert "-an" in argv and "libx264" in argv
    assert argv[argv.index("-/filter_complex") + 1] == str(tmp_path / "graph.txt")
    assert (tmp_path / "graph.txt").read_text("utf-8").count("xfade") == 2


def test_progress_reads_how_far_ffmpeg_has_got(tmp_path):
    assert loops.progress(tmp_path, 20) == 0.0
    (tmp_path / "progress.txt").write_text("out_time_us=4000000\nprogress=continue\nout_time_us=5000000\n")
    assert loops.progress(tmp_path, 20) == 0.25


def test_the_swap_replaces_the_old_video_in_one_step(tmp_path):
    new = tmp_path / "rendered.mp4"
    new.write_bytes(b"new")
    out = tmp_path / "ProPresenter Loops"
    out.mkdir()
    (out / "Pre-service loop.mp4").write_bytes(b"old")
    loops.stage(new, out, "Pre-service loop")
    assert (out / "Pre-service loop.mp4.part").read_bytes() == b"new"
    assert loops.put(out, "Pre-service loop") == out / "Pre-service loop.mp4"
    assert (out / "Pre-service loop.mp4").read_bytes() == b"new"
    assert sorted(p.name for p in out.iterdir()) == ["Pre-service loop.mp4"]


def test_a_refused_swap_keeps_the_staged_copy_for_the_next_try(tmp_path, monkeypatch):
    new = tmp_path / "rendered.mp4"
    new.write_bytes(b"new")
    (tmp_path / "Loop.mp4").write_bytes(b"old")
    loops.stage(new, tmp_path, "Loop")

    def in_use(src, dst):
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")

    monkeypatch.setattr(loops.os, "replace", in_use)
    with pytest.raises(PermissionError):
        loops.put(tmp_path, "Loop")
    assert (tmp_path / "Loop.mp4").read_bytes() == b"old"
    assert (tmp_path / "Loop.mp4.part").read_bytes() == b"new"
    loops.clear_stage(tmp_path, "Loop")
    loops.clear_stage(tmp_path, "Loop")  # already gone: fine
    assert not (tmp_path / "Loop.mp4.part").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace an open file")
def test_windows_refuses_the_swap_while_the_old_video_is_open(tmp_path):
    new = tmp_path / "rendered.mp4"
    new.write_bytes(b"new")
    (tmp_path / "Loop.mp4").write_bytes(b"old")
    loops.stage(new, tmp_path, "Loop")
    with open(tmp_path / "Loop.mp4", "rb"):
        with pytest.raises(PermissionError):
            loops.put(tmp_path, "Loop")
    loops.put(tmp_path, "Loop")
    assert (tmp_path / "Loop.mp4").read_bytes() == b"new"


def _first_and_last(path):
    gen = imageio_ffmpeg.read_frames(str(path))
    meta = next(gen)
    first = last = None
    count = 0
    for frame in gen:
        img = Image.frombytes("RGB", meta["size"], frame)
        first = first or img
        last = img
        count += 1
    return meta, first, last, count


def test_a_real_render_of_every_kind_of_screen(tmp_path):
    src = tmp_path / "PreServiceLoop"
    src.mkdir()
    portrait = Image.new("RGBA", (600, 1200), (240, 200, 40, 255))
    portrait.paste((0, 0, 0, 0), (0, 0, 600, 300))
    portrait.save(src / "1 Welcome.png")
    try:
        import pillow_heif  # noqa: F401  (registered by prep)
        Image.new("RGB", (800, 600), (30, 120, 200)).save(src / "2 Photo.heic", format="HEIF")
    except (ImportError, KeyError, OSError):
        pass
    make_gif(src / "3 Spin.gif", frames=3, ms=200)
    make_video(src / "4 Blip.mp4", 1)
    make_video(src / "5 Farewell.mp4", 3, size="640x360")
    work = loops.fresh(tmp_path / "work")
    clips, left_out = loops.plan(loops.screens(src), work, still=2)
    assert left_out == []
    out = work / "loop.mp4"
    proc = loops.start(loops.command(clips, out, work), work)
    assert proc.wait(timeout=300) == 0, loops.tail(work)
    meta, first, last, count = _first_and_last(out)
    assert meta["size"] == (1920, 1080)
    assert meta["fps"] == pytest.approx(30)
    assert count / 30 == pytest.approx(loops.length(clips), abs=0.1)
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    assert "Video: h264" in info and "Audio:" not in info
    diff = ImageStat.Stat(ImageChops.difference(first, last)).mean
    assert max(diff) < 8, "the loop's last frame should match its first, so it wraps with no jump"
    assert loops.progress(work, loops.length(clips)) == pytest.approx(1.0, abs=0.05)
