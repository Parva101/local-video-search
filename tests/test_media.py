import hashlib
import subprocess

import pytest

from video_search.media import MediaError, fingerprint, hash_source, probe, scan_sources, source_file, windows


@pytest.mark.parametrize("relative", ["../video.mp4", "/video.mp4", "C:/video.mp4", "C:video.mp4", "\\\\server\\video.mp4", "sub\\video.mp4", ""])
def test_reject_unsafe_path(tmp_path, relative):
    with pytest.raises(MediaError) as error:
        source_file(tmp_path, relative)
    assert error.value.code == "invalid_path"


def test_scan_and_hash(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "video.MP4").write_bytes(b"video content")
    (tmp_path / "readme.txt").write_text("ignored")
    assert scan_sources(tmp_path) == ["nested/video.MP4"]
    assert scan_sources(tmp_path, "nested/video.MP4") == ["nested/video.MP4"]
    path = source_file(tmp_path, "nested/video.MP4")
    assert fingerprint(path)[0] == len(b"video content")
    called = []
    assert hash_source(path, lambda: called.append(True)) == hashlib.sha256(b"video content").hexdigest()
    assert called
    with pytest.raises(MediaError, match="not supported"):
        scan_sources(tmp_path, "readme.txt")
    (tmp_path / "second.mp4").write_bytes(b"another")
    with pytest.raises(MediaError) as error:
        scan_sources(tmp_path, max_files=1)
    assert error.value.code == "file_limit"


def test_missing_and_empty_sources(tmp_path):
    with pytest.raises(MediaError) as error:
        source_file(tmp_path, "missing.mp4")
    assert error.value.code == "source_unavailable"
    with pytest.raises(MediaError) as error:
        scan_sources(tmp_path)
    assert error.value.code == "no_media"
    with pytest.raises(MediaError) as error:
        source_file(tmp_path, ".")
    assert error.value.code == "not_file"


def test_links_rejected(tmp_path):
    actual = tmp_path / "actual.mp4"
    actual.write_bytes(b"video")
    link = tmp_path / "link.mp4"
    try:
        link.symlink_to(actual)
    except OSError:
        pytest.skip("This account cannot create symlinks.")
    with pytest.raises(MediaError) as error:
        source_file(tmp_path, "link.mp4")
    assert error.value.code == "linked_source"
    with pytest.raises(MediaError):
        scan_sources(tmp_path)


@pytest.mark.parametrize("duration,expected", [(1, [(0, 1)]), (10, [(0, 10)]), (18, [(0, 10), (8, 18)]), (20, [(0, 10), (8, 18), (16, 20)])])
def test_windows(duration, expected):
    assert windows(duration) == expected


@pytest.mark.parametrize("args", [(0,), (float("inf"),), (-1,), (10, 0), (10, 5, 5), (10, 5, -1), (10, 5, float("nan"))])
def test_invalid_windows(args):
    with pytest.raises(MediaError):
        windows(*args)


def test_corrupt_media(tmp_path):
    path = tmp_path / "bad.mp4"
    path.write_bytes(b"invalid video")
    with pytest.raises(MediaError) as error:
        probe(path)
    assert error.value.code == "probe_failed"
    assert error.value.details["exit_code"] != 0
    assert error.value.details["stderr"]


@pytest.mark.parametrize("suffix", ["mp4", "mkv"])
def test_real_video_offset_timing(tmp_path, suffix):
    path = tmp_path / f"offset.{suffix}"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=4:duration=2", "-vf", "setpts=PTS+5/TB", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, timeout=30)
    metadata = probe(path)
    assert metadata["source_start_seconds"] == pytest.approx(5)
    assert 1.5 <= metadata["duration_seconds"] <= 2.1
    assert metadata["timing_origin_known"]
    assert metadata["width"] == 64
    assert not metadata["has_audio"]
    assert windows(metadata["duration_seconds"])[0][0] == 0


def test_variable_frame_rate_preserves_gap(tmp_path):
    path = tmp_path / "variable.mkv"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=4:duration=2", "-vf", "setpts=PTS+if(gte(N\\,4)\\,1/TB\\,0)+5/TB", "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, timeout=30)
    metadata = probe(path)
    assert metadata["source_start_seconds"] == pytest.approx(5)
    assert 2.5 <= metadata["duration_seconds"] <= 3.1
    assert metadata["duration_source"] == "video_packets"
def test_window_count_is_bounded():
    from video_search.media import MediaError, windows
    with pytest.raises(MediaError, match="100,000"):
        windows(1e30)

