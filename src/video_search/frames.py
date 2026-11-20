"""Sample source frames without replacing their media timestamps."""

from collections.abc import Callable
from fractions import Fraction
from io import BytesIO
import math
from pathlib import Path
import re
import subprocess

from PIL import Image, UnidentifiedImageError

from video_search.media import MediaError


def _decode(path: Path, stream: int, target: float, end: float,
            check: Callable[[], None] | None):
    if check:
        check()
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-copyts",
        "-seek_timestamp", "1", "-ss", f"{target:.12f}", "-noaccurate_seek",
        "-protocol_whitelist", "file,pipe", "-threads", "1", "-i", str(path),
        "-map", f"0:{stream}", "-frames:v", "1", "-filter_threads", "1", "-vf",
        f"trim=start={target:.12f}:end={end:.12f},showinfo,"
        "scale=w='min(512,iw)':h='min(512,ih)':force_original_aspect_ratio=decrease",
        "-fps_mode", "passthrough", "-f", "image2pipe", "-vcodec", "png",
        "-threads", "1", "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30)
    except FileNotFoundError as exc:
        raise MediaError("missing_ffmpeg", "ffmpeg is not installed or is not on PATH.", path=str(path)) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("frame_timeout", "Frame sampling exceeded 30 seconds.", path=str(path), target_pts=target) from exc
    except OSError as exc:
        raise MediaError("frame_failed", "Frame sampler could not start.", path=str(path), reason=str(exc)) from exc
    if check:
        check()
    log = result.stderr.decode("utf-8", errors="replace")
    if result.returncode:
        raise MediaError("frame_failed", "Frame sampler rejected the source.", path=str(path), target_pts=target,
                         exit_code=result.returncode, stderr=log[-4096:])
    if not result.stdout:
        return None
    base = re.search(r"config in time_base:\s*(-?\d+/\d+)", log)
    stamp = re.search(r"\bn:\s*0\s+pts:\s*(-?\d+)\s+pts_time:", log)
    if base is None or stamp is None:
        raise MediaError("frame_timing", "Frame sampler did not return a source timestamp.", path=str(path), stderr=log[-4096:])
    pts = float(int(stamp.group(1)) * Fraction(base.group(1)))
    try:
        with Image.open(BytesIO(result.stdout)) as image:
            image.load()
            frame = image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError("frame_image", "Frame sampler returned an invalid image.", path=str(path)) from exc
    return frame, pts


QUERY_IMAGE_PREPROCESS_VERSION = "pil-rgb-max512-v1"
QUERY_IMAGE_MAX_BYTES = 10 * 1024 * 1024


def prepare_query_image(data: bytes) -> Image.Image:
    """Decode a reference-image query with the same rule as indexed frames.

    Indexed frames are reduced to a maximum side of 512 pixels and converted
    to RGB before native SigLIP preprocessing. A query image repeats that rule
    with PIL. The resize implementation differs from ffmpeg, so this recipe
    carries its own version tag.
    """
    if not data:
        raise MediaError("invalid_image", "The attached reference image is empty.")
    if len(data) > QUERY_IMAGE_MAX_BYTES:
        raise MediaError("invalid_image", "The attached reference image is larger than the limit.",
                         bytes=len(data), limit_bytes=QUERY_IMAGE_MAX_BYTES)
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            frame = image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError("invalid_image", "The attached reference image is not a decodable image.") from exc
    frame.thumbnail((512, 512), Image.Resampling.LANCZOS)
    return frame


def sample_window(path: Path, metadata: dict, start: float, end: float,
                  check: Callable[[], None] | None = None, sample_count: int = 3) -> tuple[list[Image.Image], list[dict]]:
    try:
        origin = float(metadata["source_start_seconds"])
        duration = float(metadata["duration_seconds"])
        stream = metadata["video_stream_index"]
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError("frame_metadata", "Source timing metadata is missing or invalid.", path=str(path)) from exc
    if not all(math.isfinite(value) for value in (origin, duration, start, end)) or not 0 <= start < end <= duration:
        raise MediaError("frame_interval", "Frame interval must be finite and inside the source.", path=str(path), start=start, end=end)
    if not isinstance(stream, int) or isinstance(stream, bool) or stream < 0:
        raise MediaError("frame_metadata", "Video stream index is invalid.", path=str(path))
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or not 1 <= sample_count <= 8:
        raise MediaError("frame_count", "Sample count must be between one and eight.")
    frames, samples = [], []
    first = None
    for fraction in ((index + 0.5) / sample_count for index in range(sample_count)):
        requested = start + fraction * (end - start)
        decoded = _decode(path, stream, origin + requested, origin + end, check)
        selection = "at_or_after_request"
        if decoded is None:
            # A sparse clip can end before a requested slot; keep a real frame in this window.
            if first is None:
                first = _decode(path, stream, origin + start, origin + end, check)
            decoded = first
            selection = "window_first_when_no_later_frame"
        if decoded is None:
            raise MediaError("empty_window", "No decoded frame exists inside this window.", path=str(path), start=start, end=end)
        frame, pts = decoded
        source = pts - origin
        if not math.isfinite(source) or not start <= source < end:
            raise MediaError("frame_timing", "Decoded frame is outside the requested source window.", path=str(path), pts_seconds=pts, start=start, end=end)
        frames.append(frame)
        samples.append({"requested_seconds": requested, "source_seconds": source,
                        "pts_seconds": pts, "selection": selection})
    return frames, samples
