"""Prepare a fixed, local Charades-STA pilot without fetching its full archive."""

import hashlib
from io import RawIOBase
import json
import logging
import math
import os
from pathlib import Path, PurePosixPath
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import zipfile
import zlib

from video_search import media
from video_search.evaluation import validate_manifest


REVISION = "3793c625f2e251a5f19a0d59f0c83b12e386f808"
ANNOTATION_ROOT = f"https://raw.githubusercontent.com/26hzhang/VSLNet/{REVISION}/data/dataset/charades/"
ANNOTATION_HASHES = {"train": "e966fc1970cf6bc4cc73db2dd4fc10e148313810a372eef488defb0dd2ee359f",
                     "test": "fab341679c20b0917173dcffffde367a71113fe63f3a645558cef2ebfbfefb55"}
REFERENCE_METADATA_SHA256 = "42de4feae0ae2705d847776393637edafce6d8d47cfbf9ed19b8cd182d370155"
ARCHIVE_URL = "https://ai2-public-datasets.s3-us-west-2.amazonaws.com/charades/Charades_v1_480.zip"
LICENSE_URL = "https://ai2-public-datasets.s3-us-west-2.amazonaws.com/charades/Charades.zip"
SELECTION_SEED = "local-video-search-charades-pilot-v1"
MAX_READ = 4 * 1024 * 1024
MAX_MEMBER = 64 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
logger = logging.getLogger("video_search")


class DataError(ValueError):
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _request(url, *, method="GET", headers=None, limit=MAX_READ):
    parts = urlsplit(url)
    if (parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password
            or parts.fragment or (parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"})):
        raise DataError("Dataset URL must be HTTPS, or local HTTP for tests", url=url)
    params = {"url": url, "method": method, "headers": headers or {}, "read_limit": limit}
    request = Request(url, method=method, headers={"Accept-Encoding": "identity", **(headers or {})})
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=60) as response:
                body = b"" if method == "HEAD" else response.read(limit + 1)
                if len(body) > limit:
                    raise DataError("Dataset reply exceeded its read limit", params=params, status=response.status,
                                    response_body="[binary body omitted]", request_id=response.headers.get("x-amz-request-id"))
                return response.status, response.headers, body
        except HTTPError as exc:
            details = {"params": params, "status": exc.code, "response_body": exc.read(4096).decode("utf-8", errors="replace"),
                       "request_id": exc.headers.get("x-amz-request-id") or exc.headers.get("X-Request-ID"), "attempt": attempt + 1}
            exc.close()
            retry = exc.code == 429 or exc.code >= 500
            cause = exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            details = {"params": params, "status": None, "response_body": str(exc), "request_id": None, "attempt": attempt + 1}
            retry, cause = True, exc
        if not retry or attempt == 2:
            raise DataError("Dataset request failed", **details) from cause
        logger.warning("benchmark_download_retry", extra={"fields": details})
        time.sleep(.5 * 2 ** attempt)


class RangeReader(RawIOBase):
    """A bounded, immutable HTTP file for the standard-library ZIP reader."""

    def __init__(self, url):
        super().__init__()
        status, headers, _ = _request(url, method="HEAD", limit=0)
        length, etag = headers.get("Content-Length", ""), headers.get("ETag", "")
        if status != 200 or not length.isdecimal() or int(length) <= 0 or not etag or etag.startswith("W/"):
            raise DataError("Archive HEAD needs its exact length and strong ETag", params={"url": url}, status=status,
                            response_body="", request_id=headers.get("x-amz-request-id"))
        self.url, self.length, self.etag, self.position = url, int(length), etag, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in {0, 1, 2}:
            raise ValueError("Unknown seek origin")
        position = offset + (self.position if whence == 1 else self.length if whence == 2 else 0)
        if not isinstance(position, int) or not 0 <= position <= self.length:
            raise DataError("Archive seek is outside its bounds", position=position, length=self.length)
        self.position = position
        return position

    def read(self, size=-1):
        if self.closed:
            raise ValueError("Archive reader is closed")
        size = self.length - self.position if size is None or size < 0 else min(size, self.length - self.position)
        if size > MAX_READ:
            raise DataError("Archive read exceeds 4 MiB", position=self.position, size=size)
        if not size:
            return b""
        start, end = self.position, self.position + size - 1
        status, headers, body = _request(self.url, headers={"Range": f"bytes={start}-{end}", "If-Match": self.etag}, limit=size)
        if (status != 206 or headers.get("Content-Range") != f"bytes {start}-{end}/{self.length}"
                or headers.get("ETag") != self.etag or headers.get("Content-Encoding", "identity") != "identity"
                or headers.get("Content-Length") != str(size) or len(body) != size):
            raise DataError("Archive range reply is changed, incomplete or ignored", params={"url": self.url, "start": start, "end": end},
                            status=status, response_body="[binary body omitted]", request_id=headers.get("x-amz-request-id"))
        self.position += size
        return body


def _safe_member(info):
    path = PurePosixPath(info.filename)
    if (not info.filename or "\\" in info.filename or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]
            or (info.external_attr >> 16) & 0o170000 == 0o120000):
        raise DataError("Unsafe archive path", member=info.filename)
    if (info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            or not 0 <= info.file_size <= MAX_MEMBER or not 0 <= info.compress_size <= MAX_MEMBER):
        raise DataError("Unsupported or oversized archive member", member=info.filename,
                        compressed_bytes=info.compress_size, bytes=info.file_size)


def _file_proof(path):
    digest, crc, size = hashlib.sha256(), 0, 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            crc = zlib.crc32(block, crc)
            size += len(block)
    return {"sha256": digest.hexdigest(), "crc32": crc, "bytes": size}


def download_member(archive, info, destination):
    _safe_member(info)
    destination = Path(destination)
    if destination.is_symlink():
        raise DataError("Existing destination is a link", path=str(destination))
    if destination.exists():
        proof = _file_proof(destination)
        if proof["bytes"] != info.file_size or proof["crc32"] != info.CRC:
            raise DataError("Existing file differs from the selected archive member", path=str(destination), member=info.filename)
        return proof
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    if partial.exists():
        raise DataError("Incomplete download exists; preserve it before restarting this member", path=str(partial))
    count = 0
    with partial.open("xb") as output, archive.open(info) as source:
        while block := source.read(1024 * 1024):
            count += len(block)
            if count > info.file_size or count > MAX_MEMBER:
                raise DataError("Inflated member exceeded its declared size", member=info.filename)
            output.write(block)
    proof = _file_proof(partial)
    if count != info.file_size or proof["crc32"] != info.CRC:
        raise DataError("Downloaded member failed size or CRC validation", member=info.filename)
    # Match upload publication: make the complete file visible without overwriting a destination.
    os.link(partial, destination)
    partial.unlink()
    return proof


def parse_annotations(data, split):
    if split not in {"train", "test"}:
        raise DataError("Unknown Charades split", split=split)
    rows = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DataError("Annotations are not UTF-8") from exc
    for number, line in enumerate(text.splitlines(), 1):
        parts = line.split("##", 1)
        fields = parts[0].split()
        if len(parts) != 2 or len(fields) != 3 or not re.fullmatch(r"[A-Za-z0-9]+", fields[0]) or not parts[1].strip():
            raise DataError("Invalid annotation line", split=split, line=number)
        try:
            start, end = map(float, fields[1:])
        except ValueError as exc:
            raise DataError("Invalid annotation timestamps", split=split, line=number) from exc
        if not math.isfinite(start) or not math.isfinite(end) or not start < end:
            raise DataError("Invalid annotation interval", split=split, line=number)
        rows.append({"id": f"{split}:{fields[0]}:{number}", "video_id": fields[0], "query": parts[1].strip(),
                     "start_seconds": start, "end_seconds": end})
    if not rows:
        raise DataError("Annotations contain no queries", split=split)
    return rows


def select_videos(rows, split, count):
    videos = sorted({row["video_id"] for row in rows}, key=lambda video: hashlib.sha256(f"{SELECTION_SEED}:{split}:{video}".encode()).hexdigest())
    if type(count) is not int or not 1 <= count <= len(videos):
        raise DataError("Selection count is outside the available video population", count=count)
    return videos[:count]


def make_manifest(split, rows, videos):
    queries = []
    for row in rows:
        video = row["video_id"]
        if video not in videos:
            continue
        duration = videos[video]["annotation_duration_seconds"]
        start, end = max(0, row["start_seconds"]), min(row["end_seconds"], duration)
        if not math.isfinite(duration) or duration <= 0 or start >= end:
            raise DataError("Author preprocessing produced invalid target bounds", query_id=row["id"],
                            raw_start=row["start_seconds"], raw_end=row["end_seconds"], annotation_duration=duration)
        queries.append({"id": row["id"], "query": row["query"], "scope_video_ids": [video],
                        "targets": [{"video_id": video, "start_seconds": start, "end_seconds": end}],
                        "raw_targets": [{"video_id": video, "start_seconds": row["start_seconds"], "end_seconds": row["end_seconds"]}]})
    result = {"name": "charades-sta-fixed-pilot-v1", "split": "development" if split == "train" else "held-out-pilot",
              "provenance": f"VSLNet paper-author annotation copy {REVISION}; not byte-compared with original TALL downloads. "
                            f"Selected by SHA256({SELECTION_SEED}:split:video_id). Canonical targets follow the pinned author's util/data_gen.py: "
                            "start=max(0,raw_start), end=min(raw_end,charades.json duration); raw_targets are preserved. "
                            "Actual decoded media duration stays separate; predictions must remain inside it. "
                            "Local licensed data; no redistribution. This is a subset, not full-benchmark SOTA.",
              "videos": videos, "queries": queries}
    validate_manifest(result)
    return result


def _write_once(path, data):
    raw = data if isinstance(data, bytes) else (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise DataError("Existing preparation record differs; never overwrite it", path=str(path))
        return
    with path.open("xb") as output:
        output.write(raw)


def prepare(output):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "media").is_symlink():
        raise DataError("Media output directory must not be a link", path=str(root / "media"))
    annotations, selected = {}, {}
    for split, count in [("train", 20), ("test", 25)]:
        url = ANNOTATION_ROOT + f"charades_sta_{split}.txt"
        status, _, data = _request(url, limit=2 * 1024 * 1024)
        if status != 200 or hashlib.sha256(data).hexdigest() != ANNOTATION_HASHES[split]:
            raise DataError("Pinned annotation hash differs", url=url, status=status)
        _write_once(root / f"charades_sta_{split}.txt", data)
        annotations[split] = parse_annotations(data, split)
        selected[split] = select_videos(annotations[split], split, count)
    if set(selected["train"]) & set(selected["test"]):
        raise DataError("Selected source videos overlap between splits")
    metadata_url = ANNOTATION_ROOT + "charades.json"
    status, _, raw_metadata = _request(metadata_url, limit=2 * 1024 * 1024)
    if status != 200 or hashlib.sha256(raw_metadata).hexdigest() != REFERENCE_METADATA_SHA256:
        raise DataError("Pinned reference metadata hash differs", url=metadata_url, status=status)
    _write_once(root / "reference.charades.json", raw_metadata)
    reference_metadata = json.loads(raw_metadata)
    with RangeReader(LICENSE_URL) as remote, zipfile.ZipFile(remote) as archive:
        license_info = archive.getinfo("Charades/license.txt")
        if license_info.file_size != 1177 or license_info.CRC != 4255669424:
            raise DataError("Primary license identity changed")
        license_proof = download_member(archive, license_info, root / "license.txt")
    videos, proofs = {"train": {}, "test": {}}, {}
    with RangeReader(ARCHIVE_URL) as remote, zipfile.ZipFile(remote) as archive:
        entries = {}
        for info in archive.infolist():
            if info.filename.endswith(".mp4"):
                video = PurePosixPath(info.filename).stem
                if video in entries:
                    raise DataError("Duplicate archive video ID", video_id=video)
                entries[video] = info
        missing = [video for split in selected.values() for video in split if video not in entries]
        if missing:
            raise DataError("Selected videos are missing from the archive", video_ids=missing)
        chosen = [entries[video] for split in selected.values() for video in split]
        for info in chosen:
            _safe_member(info)
        if sum(info.file_size for info in chosen) > MAX_TOTAL:
            raise DataError("Selected media exceeds the 1 GiB cap")
        provenance = {"archive_url": ARCHIVE_URL, "archive_length": remote.length, "archive_etag": remote.etag,
                      "annotation_revision": REVISION, "annotation_sha256": ANNOTATION_HASHES,
                      "reference_metadata_url": metadata_url, "reference_metadata_sha256": REFERENCE_METADATA_SHA256,
                      "selection_seed": SELECTION_SEED, "selected_video_ids": selected, "license_url": LICENSE_URL,
                      "license_proof": license_proof,
                      "media_bytes": sum(info.file_size for info in chosen), "compressed_media_bytes": sum(info.compress_size for info in chosen)}
        _write_once(root / "selection.json", provenance)
        for split, ids in selected.items():
            for video in ids:
                info, target = entries[video], root / "media" / (video + ".mp4")
                proof = download_member(archive, info, target)
                metadata = media.probe(target)
                reference = reference_metadata[video]
                expected_subset = "training" if split == "train" else "testing"
                if reference["subset"] != expected_subset:
                    raise DataError("Reference source split differs from annotation split", video_id=video,
                                    expected=expected_subset, actual=reference["subset"])
                videos[split][video] = {"duration_seconds": metadata["duration_seconds"],
                                       "annotation_duration_seconds": reference["duration"], "sha256": proof["sha256"],
                                       "path": "media/" + target.name, "source_start_seconds": metadata["source_start_seconds"]}
                proofs[video] = {**proof, "member": info.filename, "compressed_bytes": info.compress_size,
                                 "header_offset": info.header_offset, "metadata": metadata}
                logger.info("benchmark_media_verified", extra={"fields": {"video_id": video, "split": split, "proof": proof}})
    if {v["sha256"] for v in videos["train"].values()} & {v["sha256"] for v in videos["test"].values()}:
        raise DataError("Decoded media hashes overlap between source splits")
    manifests = {split: make_manifest(split, annotations[split], items) for split, items in videos.items()}
    windows = sum(len(media.windows(v["duration_seconds"])) for split in videos.values() for v in split.values())
    query_count = sum(len(m["queries"]) for m in manifests.values())
    provenance.update(files=proofs, index_window_count=windows, query_count=query_count,
                      three_policy_three_check_max_calls=windows + query_count * 3 * 3,
                      call_cap=1500, includes_model_calls=False,
                      budget_note="This is a logical-call estimate. The runtime must also count HTTP attempts and stop at the approved cap.")
    if provenance["three_policy_three_check_max_calls"] > 1500:
        raise DataError("Frozen pilot exceeds its 1500-call estimate; revise scope before inference", estimate=provenance["three_policy_three_check_max_calls"])
    for split, document in manifests.items():
        _write_once(root / f"{split}.manifest.json", document)
    _write_once(root / "provenance.json", provenance)
    return {"output": str(root), "videos": len(proofs), "queries": query_count, "index_windows": windows,
            "maximum_model_calls": provenance["three_policy_three_check_max_calls"], "model_calls_used": 0}
