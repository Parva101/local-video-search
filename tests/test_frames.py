import subprocess

import pytest

from video_search.frames import sample_window
from video_search.media import MediaError, probe


def make_video(path, *, offset=0, rate=4, duration=2, size="64x64", variable=False):
    timing = ["-output_ts_offset", str(offset)]
    if variable:
        timing = ["-vf", f"setpts=PTS+if(gte(N\\,4)\\,1/TB\\,0)+{offset}/TB", "-fps_mode", "vfr"]
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        f"testsrc=size={size}:rate={rate}:duration={duration}", *timing,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True, timeout=30)


@pytest.mark.parametrize("suffix", ["mp4", "mkv"])
def test_offset_samples_keep_actual_pts(tmp_path, suffix):
    path = tmp_path / f"offset.{suffix}"
    make_video(path, offset=5)
    metadata = probe(path)
    checks = []
    duration = metadata["duration_seconds"]
    images, samples = sample_window(path, metadata, 0, duration, lambda: checks.append(True))
    assert len(images) == len(samples) == 3
    assert [item["requested_seconds"] for item in samples] == pytest.approx([duration / 6, duration / 2, duration * 5 / 6])
    assert [item["source_seconds"] for item in samples] == pytest.approx([0.5, 1, 1.75])
    assert [item["pts_seconds"] for item in samples] == pytest.approx([5.5, 6, 6.75])
    assert all(item["selection"] == "at_or_after_request" for item in samples)
    assert all(image.size == (64, 64) and image.mode == "RGB" for image in images)
    assert len(checks) == 6


def test_large_image_is_bounded(tmp_path):
    path = tmp_path / "large.mp4"
    make_video(path, size="1024x768")
    metadata = probe(path)
    images, _ = sample_window(path, metadata, 0, metadata["duration_seconds"])
    assert all(image.size == (512, 384) for image in images)


def test_sparse_slots_keep_duplicate_occurrences(tmp_path):
    path = tmp_path / "sparse.mp4"
    make_video(path, rate=1, duration=1)
    metadata = probe(path)
    images, samples = sample_window(path, metadata, 0, metadata["duration_seconds"])
    assert len(images) == 3
    assert [item["source_seconds"] for item in samples] == [0, 0, 0]
    assert all(item["selection"] == "window_first_when_no_later_frame" for item in samples)


def test_variable_rate_gaps_keep_real_frame_times(tmp_path):
    path = tmp_path / "variable.mkv"
    make_video(path, offset=5, variable=True)
    images, samples = sample_window(path, probe(path), 0, 3)
    assert len(images) == 3
    assert [item["source_seconds"] for item in samples] == pytest.approx([0.5, 2, 2.5])
    assert [item["pts_seconds"] for item in samples] == pytest.approx([5.5, 7, 7.5])


def test_empty_window_does_not_borrow_a_frame(tmp_path):
    path = tmp_path / "variable.mkv"
    make_video(path, offset=5, variable=True)
    with pytest.raises(MediaError) as error:
        sample_window(path, probe(path), 1, 1.5)
    assert error.value.code == "empty_window"


def test_late_window_keeps_source_time(tmp_path):
    path = tmp_path / "longer.mp4"
    make_video(path, offset=5, duration=12)
    _, samples = sample_window(path, probe(path), 4, 6)
    assert [item["source_seconds"] for item in samples] == pytest.approx([4.5, 5, 5.75])
    assert [item["pts_seconds"] for item in samples] == pytest.approx([9.5, 10, 10.75])


def test_corrupt_video_is_not_an_empty_window(tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a video")
    metadata = {"duration_seconds": 2, "source_start_seconds": 0, "video_stream_index": 0}
    with pytest.raises(MediaError) as error:
        sample_window(path, metadata, 0, 2)
    assert error.value.code == "frame_failed"
    assert error.value.details["exit_code"] != 0


@pytest.mark.parametrize("start,end", [(-1, 1), (0, 3), (1, 1), (0, float("nan"))])
def test_invalid_intervals_are_rejected(tmp_path, start, end):
    metadata = {"duration_seconds": 2, "source_start_seconds": 0, "video_stream_index": 0}
    with pytest.raises(MediaError) as error:
        sample_window(tmp_path / "unused.mp4", metadata, start, end)
    assert error.value.code == "frame_interval"
