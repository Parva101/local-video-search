"""Read-only media import and source-relative time windows."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import tempfile
from collections.abc import Callable


UPLOAD_PREFIX = "/__uploads/"
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mts", ".m2ts", ".mpeg", ".mpg"}


class MediaError(ValueError):
    def __init__(self, code: str, message: str, **details: object):
        super().__init__(message)
        self.code = code
        self.details = details


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _source_path(root: Path, relative: str) -> Path:
    if not relative or "\x00" in relative or "\\" in relative:
        raise MediaError("invalid_path", "Use a relative path with forward slashes.", path=relative)
    posix = PurePosixPath(relative)
    if posix.is_absolute() or PureWindowsPath(relative).drive or ".." in posix.parts:
        raise MediaError("invalid_path", "Source path must stay inside the import root.", path=relative)
    try:
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise MediaError("invalid_root", "Import root is not a directory.")
        path = root
        for part in posix.parts:
            path = path / part
            if _is_link(path):
                raise MediaError("linked_source", "Source links and junctions are not allowed.", path=relative)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise MediaError("invalid_path", "Source path leaves the import root.", path=relative)
        return resolved
    except OSError as exc:
        raise MediaError("source_unavailable", "Source path cannot be read.", path=relative, reason=str(exc)) from exc


def source_file(root: Path, relative: str, *, upload_root: Path | None = None) -> Path:
    if upload_root is not None and relative.startswith(UPLOAD_PREFIX):
        root, relative = upload_root, relative.removeprefix(UPLOAD_PREFIX)
    path = _source_path(root, relative)
    if not path.is_file():
        raise MediaError("not_file", "Source must be a regular file.", path=relative)
    return path


def scan_sources(root: Path, relative: str = ".", max_files: int = 10000) -> list[str]:
    if max_files < 1:
        raise MediaError("invalid_limit", "File limit must be positive.")
    selected = _source_path(root, relative)
    root = root.resolve(strict=True)
    if selected.is_file():
        if selected.suffix.lower() not in MEDIA_EXTENSIONS:
            raise MediaError("unsupported_media", "Source file type is not supported.", path=relative)
        return [selected.relative_to(root).as_posix()]
    if not selected.is_dir():
        raise MediaError("not_directory", "Source must be a file or directory.", path=relative)
    found: list[str] = []
    pending = [selected]
    try:
        while pending:
            directory = pending.pop()
            for path in directory.iterdir():
                if _is_link(path):
                    raise MediaError("linked_source", "Source links and junctions are not allowed.", path=path.relative_to(root).as_posix())
                if path.is_dir():
                    pending.append(path)
                elif path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
                    found.append(path.relative_to(root).as_posix())
                    if len(found) > max_files:
                        raise MediaError("file_limit", "Import exceeds the file limit; select a smaller folder.", limit=max_files)
    except OSError as exc:
        raise MediaError("source_unavailable", "Source directory cannot be scanned.", path=relative, reason=str(exc)) from exc
    if not found:
        raise MediaError("no_media", "No supported video files were found.", path=relative)
    return sorted(found)


def fingerprint(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns
    except OSError as exc:
        raise MediaError("source_unavailable", "Source file cannot be read.", path=str(path), reason=str(exc)) from exc


def hash_source(path: Path, progress: Callable[[], None] | None = None) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
                if progress:
                    progress()
    except OSError as exc:
        raise MediaError("source_unavailable", "Source file cannot be hashed.", path=str(path), reason=str(exc)) from exc
    return digest.hexdigest()


def _run_probe(path: Path, entries: list[str], output=None):
    command = ["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", *entries, str(path)]
    try:
        result = subprocess.run(command, stdout=output or subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except FileNotFoundError as exc:
        raise MediaError("missing_ffprobe", "ffprobe is not installed or is not on PATH.", path=str(path)) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("probe_timeout", "Media probe exceeded 120 seconds.", path=str(path)) from exc
    except OSError as exc:
        raise MediaError("probe_failed", "Media probe could not start.", path=str(path), reason=str(exc)) from exc
    if result.returncode:
        raise MediaError("probe_failed", "Media probe rejected the source.", path=str(path), exit_code=result.returncode, stderr=result.stderr.decode("utf-8", errors="replace")[-4096:])
    return result


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def _packet_duration(path: Path, stream_index: int, origin: float) -> float:
    # Container duration can include a non-zero timestamp origin; packet times do not.
    with tempfile.TemporaryFile(mode="w+b") as output:
        _run_probe(path, ["-select_streams", str(stream_index), "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0"], output)
        output.seek(0)
        end = None
        for raw in output:
            row = next(csv.reader([raw.decode("utf-8", errors="replace")]))
            if not row:
                continue
            pts = _number(row[0])
            duration = _number(row[1]) if len(row) > 1 else None
            if pts is not None and duration is not None and duration > 0:
                end = max(end if end is not None else pts, pts + duration)
        if end is None:
            raise MediaError("unknown_duration", "Video packet timing does not provide a duration.", path=str(path))
        return end - origin


def probe(path: Path) -> dict:
    result = _run_probe(path, ["-show_streams", "-show_format", "-of", "json"])
    try:
        document = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MediaError("invalid_probe", "Media probe returned invalid JSON.", path=str(path)) from exc
    streams = document.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")), None)
    if video is None:
        raise MediaError("no_video", "Source has no video stream.", path=str(path))
    start = _number(video.get("start_time"))
    origin = start if start is not None else 0.0
    duration = _number(video.get("duration"))
    duration_source = "video_stream"
    if duration is None or duration <= 0:
        duration = _packet_duration(path, video["index"], origin)
        duration_source = "video_packets"
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError("invalid_duration", "Video duration must be finite and positive.", path=str(path))
    return {
        "duration_seconds": duration,
        "duration_source": duration_source,
        "source_start_seconds": origin,
        "timing_origin_known": start is not None,
        "time_base": video.get("time_base"),
        "video_stream_index": video["index"],
        "codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
    }


def windows(duration: float, length: float = 10, overlap: float = 2) -> list[tuple[float, float]]:
    if not all(math.isfinite(value) for value in (duration, length, overlap)) or duration <= 0 or length <= 0 or overlap < 0 or overlap >= length:
        raise MediaError("invalid_windows", "Duration and length must be positive; overlap must be at least zero and below length.")
    if (duration - length) / (length - overlap) > 99999:
        raise MediaError("window_limit", "Source needs more than 100,000 windows; split it into smaller files.")
    result = []
    index = 0
    while True:
        start = index * (length - overlap)
        end = min(start + length, duration)
        result.append((start, end))
        if end >= duration:
            return result
        index += 1
