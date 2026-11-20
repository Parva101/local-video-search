"""Prepare a private, immutable SDST Charades snapshot. CPU only; no pickle loads."""

import argparse
from contextlib import contextmanager
import hashlib
from html.parser import HTMLParser
import json
import logging
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import time
from urllib.parse import urljoin, urlparse
import uuid
import zipfile

import numpy as np
import requests

COMMIT = "ea8fa9fe1158c0bcdb60df2861450f4b69362f3e"
FILE_ID = "1VPz-wrreNWHbTywUrNHvavODKMjZQWP9"
ARCHIVE_BYTES = 27292943823
DIRECTORY_OFFSET, DIRECTORY_BYTES = 27284393612, 8550113
DIRECTORY_SHA256 = "1ca3225f100b87fe93a4dd72254caefb95e76db2750eac1fd046c537d7dff082"
CHECKPOINT_BYTES = 53916069
CHECKPOINT_BLOB = "5da678c2633f80c77ae3b2f5cf1eb4d645b7d326"
LABELS = {
    "charades_train.jsonl": (12404, "cc061d290f5be0735ecfaf80d9f9d09a5032f8b95faef114fe6ce21add2df9aa"),
    "charades_test.jsonl": (3720, "fbf26493b5b1b7c08e3cb0b79e3ef400709229205cfea24745798292ba7eb7d6"),
}
logger = logging.getLogger("sdst_prepare")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def source_identity(root):
    upstream = (root / "upstream").resolve()
    record = json.loads((root / "source-identity.json").read_bytes())
    if (record.get("source_commit") != COMMIT
            or (upstream / ".git/HEAD").read_text(encoding="ascii").strip() != COMMIT
            or not isinstance(record.get("files"), dict) or not record["files"]):
        raise ValueError("Source identity must describe the pinned detached checkout")
    for name, expected in record["files"].items():
        path = PurePosixPath(name)
        target = upstream.joinpath(*path.parts)
        if (not name or not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name
                or ":" in name or path.parts[0] == ".git" or not target.resolve().is_relative_to(upstream)):
            raise ValueError(f"Unsafe source manifest path: {name}")
        if not target.is_file() or sha256(target) != expected:
            raise ValueError(f"Source file differs from its host Git identity: {name}")
    return record["files"]


def archive_identity(path):
    if path.stat().st_size != ARCHIVE_BYTES:
        raise ValueError("Archive byte count differs from the observed release")
    with path.open("rb") as stream:
        stream.seek(DIRECTORY_OFFSET)
        if hashlib.sha256(stream.read(DIRECTORY_BYTES)).hexdigest() != DIRECTORY_SHA256:
            raise ValueError("Archive central directory differs from the observed release")
    return {"bytes": ARCHIVE_BYTES, "sha256": sha256(path),
            "hash_source": "first-local-snapshot; not author-provided",
            "directory_sha256": DIRECTORY_SHA256, "drive_file_id": FILE_ID}


class Confirmation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action, self.params = None, {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "download-form":
            self.action = attrs.get("action")
        if tag == "input" and attrs.get("type") == "hidden" and "name" in attrs:
            self.params[attrs["name"]] = attrs.get("value", "")


def google_response(session, url, params):
    for redirect in range(6):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"drive.google.com", "drive.usercontent.google.com"}:
            raise ValueError("Download redirect leaves the allowed HTTPS Google hosts")
        response = session.get(url, params=params, stream=True, timeout=(30, 180), allow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        url, params = urljoin(response.url, response.headers["Location"]), None
        response.close()
    raise ValueError("Too many Google download redirects")


def download_archive(target, session=None, sleep=time.sleep):
    """Never resume: each attempt has one fresh, bounded full-body stream."""
    if target.exists():
        record = json.loads(target.with_suffix(".json").read_bytes())
        actual = archive_identity(target)
        if record != actual:
            raise ValueError("Cached archive differs from its immutable local identity")
        return actual
    session = session or requests.Session()
    url = "https://drive.usercontent.google.com/download"
    for attempt in range(3):
        partial = target.with_name(target.name + "." + uuid.uuid4().hex + ".partial")
        response, prefix = None, b""
        try:
            print(json.dumps({"event": "archive_download_start", "attempt": attempt + 1,
                              "expected_bytes": ARCHIVE_BYTES}), flush=True)
            params = {"id": FILE_ID, "export": "download"}
            for confirmation in range(2):
                response = google_response(session, url, params)
                if response.status_code != 200:
                    prefix = response.raw.read(65537, decode_content=True)
                    raise ValueError("Google download returned an unsuccessful status")
                content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                if content_type != "text/html":
                    break
                prefix = response.raw.read(65537, decode_content=True)
                response.close()
                if confirmation or len(prefix) > 65536:
                    raise ValueError("Unexpected or oversized Google confirmation page")
                form = Confirmation()
                form.feed(prefix.decode("utf-8"))
                if (form.action != url or form.params.get("id") != FILE_ID
                        or not form.params.get("confirm")):
                    raise ValueError("Unexpected Google confirmation form")
                params = form.params
            if (response.status_code != 200 or content_type not in {
                    "application/zip", "application/octet-stream", "application/x-zip-compressed"}
                    or response.headers.get("Content-Length") != str(ARCHIVE_BYTES)
                    or response.headers.get("Content-Encoding", "identity") != "identity"):
                raise ValueError("Expected one complete, unencoded ZIP response with the exact byte count")
            size, next_progress = 0, 1024 ** 3
            with partial.open("xb") as stream:
                for block in response.iter_content(1024 ** 2):
                    if not size and block[:4] != b"PK\x03\x04":
                        raise ValueError("Download body is not a ZIP archive")
                    size += len(block)
                    if size > ARCHIVE_BYTES:
                        raise ValueError("Download exceeds the declared archive size")
                    stream.write(block)
                    if size >= next_progress:
                        print(json.dumps({"event": "archive_download_progress", "attempt": attempt + 1,
                                          "bytes": size, "expected_bytes": ARCHIVE_BYTES}), flush=True)
                        next_progress += 1024 ** 3
                stream.flush()
                os.fsync(stream.fileno())
            record = archive_identity(partial)
            os.link(partial, target)
            partial.unlink()
            write_json(target.with_suffix(".json"), record)
            return record
        except (requests.RequestException, ValueError, OSError) as exc:
            fields = {"file_id": FILE_ID, "attempt": attempt + 1, "partial": partial.name,
                      "status": response.status_code if response is not None else None,
                      "response_body": {"observed_bytes": len(prefix), "sha256": hashlib.sha256(prefix).hexdigest()},
                      "correlation_id": response.headers.get("X-Request-ID") if response is not None else None,
                      "error_type": type(exc).__name__}
            write_json(partial.with_suffix(".failure.json"), fields)
            exc.add_note(json.dumps(fields))
            if attempt == 2:
                raise
            logger.warning("archive_download_retry", extra={"fields": fields})
            sleep(2 ** attempt)
        finally:
            if response is not None:
                response.close()
    raise AssertionError("Download attempts exhausted without a result")


def extract_charades(archive, destination, member_limit=64 * 1024 ** 2, total_limit=8 * 1024 ** 3):
    """Read each selected member to EOF, which also verifies its ZIP CRC."""
    records, seen, total = {}, set(), 0
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            name, path = member.orig_filename, PurePosixPath(member.orig_filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or "\x00" in member.orig_filename or ":" in name):
                raise ValueError(f"Unsafe ZIP member: {name}")
            if name in seen:
                raise ValueError(f"Duplicate ZIP member: {name}")
            seen.add(name)
            if any(part.startswith("._") or part == "__MACOSX" for part in path.parts):
                continue
            selected = (name in {"data/charades/" + label for label in LABELS}
                        or (len(path.parts) == 4 and path.parts[:2] == ("data", "charades")
                            and path.parts[2] in {"vid_feats", "txt_feats"} and path.suffix == ".npz"))
            mode = member.external_attr >> 16
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR} or member.flag_bits & 1:
                raise ValueError(f"Unsafe ZIP member type or encryption: {name}")
            if not selected:
                continue
            if (member.is_dir() or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                    or not 0 < member.file_size <= member_limit):
                raise ValueError(f"Invalid ZIP member type, encryption or size: {name}")
            total += member.file_size
            if total > total_limit:
                raise ValueError("Selected ZIP members exceed the extraction limit")
            target = destination.joinpath(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output, 1024 ** 2)
            if target.stat().st_size != member.file_size:
                raise ValueError(f"Incomplete ZIP member: {name}")
            records[str(path.relative_to("data"))] = {
                "bytes": member.file_size, "sha256": sha256(target), "crc32": f"{member.CRC:08x}"}
    return records


def validate_features(path, kind):
    key = "visual_feats_interm_pooled" if kind == "vid_feats" else "text_feats"
    with zipfile.ZipFile(path) as inner:
        if (len(inner.namelist()) != len(set(inner.namelist()))
                or sum(info.file_size for info in inner.infolist()) > 64 * 1024 ** 2):
            raise ValueError(f"Unsafe or oversized NPZ payload: {path}")
    with np.load(path, allow_pickle=False) as archive:
        if archive.files != [key]:
            raise ValueError(f"Unexpected NPZ keys: {path}")
        array = archive[key]
        if array.ndim != 3:
            raise ValueError(f"Expected a three-dimensional NPZ tensor: {path}")
        expected = (array.shape[0], 5, 768) if kind == "vid_feats" else (5, array.shape[1], 1024)
        length = array.shape[0] if kind == "vid_feats" else array.shape[1]
        if (expected != array.shape or not 1 <= length <= 512
                or array.dtype != np.dtype("float32") or not np.isfinite(array).all()):
            raise ValueError(f"Invalid NPZ shape, length, dtype or values: {path}")
        return list(array.shape)


def validate_tree(data, records, labels=LABELS, counts=(9848, 16124)):
    qids, vids, summary = set(), set(), {}
    for name, (count, expected_hash) in labels.items():
        path = data / "charades" / name
        if sha256(path) != expected_hash:
            raise ValueError(f"Label SHA-256 differs: {name}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != count:
            raise ValueError(f"Label query count differs: {name}")
        local = {str(row["qid"]) for row in rows}
        if len(local) != count or qids & local:
            raise ValueError("Duplicate query identity")
        qids.update(local)
        vids.update(row["vid"] for row in rows)
        summary[name] = {"queries": count, "sources": len({row["vid"] for row in rows}),
                         "duration_under_5": sum(row["duration"] < 5 for row in rows),
                         "subsecond_targets": sum(end - start < 1 for row in rows for start, end in row["relevant_windows"]),
                         "reversed_targets": sum(end < start for row in rows for start, end in row["relevant_windows"]),
                         "out_of_bounds_targets": sum(start < 0 or end > row["duration"] for row in rows for start, end in row["relevant_windows"])}
    for kind, required, count in zip(("vid_feats", "txt_feats"), (vids, qids), counts):
        available = {path.stem for path in (data / "charades" / kind).glob("*.npz")}
        if len(available) != count or not required <= available:
            raise ValueError(f"Feature count or complete label coverage differs: {kind}")
        for identity in sorted(available):
            relative = f"charades/{kind}/{identity}.npz"
            path = data / relative
            if relative not in records or sha256(path) != records[relative]["sha256"]:
                raise ValueError(f"Feature differs from its extracted member: {relative}")
            records[relative]["shape"] = validate_features(path, kind)
    return {"splits": summary, "video_files": counts[0], "text_files": counts[1],
            "covered_sources": len(vids), "covered_queries": len(qids), "annotation_changes": 0}


@contextmanager
def preparation_lock(root):
    import fcntl
    with (root / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def prepare(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with preparation_lock(root):
        upstream = root / "upstream"
        source_hashes = source_identity(root)
        checkpoint = upstream / "checkpoints_sdst/checkpoint_charades_sta.pth"
        blob = hashlib.sha1(f"blob {CHECKPOINT_BYTES}\0".encode())
        with checkpoint.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 ** 2), b""):
                blob.update(block)
        if checkpoint.stat().st_size != CHECKPOINT_BYTES or blob.hexdigest() != CHECKPOINT_BLOB:
            raise ValueError("Pinned checkpoint Git blob identity differs")
        downloads = root / "downloads"
        downloads.mkdir(exist_ok=True)
        archive = downloads / "data_sdst.zip"
        identity = download_archive(archive)
        print(json.dumps({"event": "archive_snapshot_ready", **identity}), flush=True)
        data = root / "data"
        if data.exists():
            report = json.loads((data / "preparation.json").read_bytes())
            records = json.loads((data / "members.json").read_bytes())
            if (report["source_commit"] != COMMIT or report["archive"] != identity
                    or report["source_manifest_sha256"] != sha256(data / "source-files.json")
                    or json.loads((data / "source-files.json").read_bytes()) != source_hashes
                    or report["member_manifest_sha256"] != sha256(data / "members.json")
                    or report["checkpoint"]["sha256"] != sha256(checkpoint)
                    or validate_tree(data, records) != report["validation"]):
                raise ValueError("Published preparation differs from its immutable report")
            if not (root / "preparation.json").exists():
                os.link(data / "preparation.json", root / "preparation.json")
            elif sha256(root / "preparation.json") != sha256(data / "preparation.json"):
                raise ValueError("Preparation report differs from its published copy")
            print(json.dumps({"event": "preparation_verified", "archive_sha256": identity["sha256"]}), flush=True)
            return
        stage = root / ("staging-" + uuid.uuid4().hex)
        stage.mkdir()
        print(json.dumps({"event": "extraction_start", "stage": stage.name}), flush=True)
        records = extract_charades(archive, stage / "data")
        print(json.dumps({"event": "validation_start", "member_files": len(records)}), flush=True)
        validation = validate_tree(stage / "data", records)
        print(json.dumps({"event": "validation_ready", "covered_queries": validation["covered_queries"],
                          "video_files": validation["video_files"], "text_files": validation["text_files"]}), flush=True)
        write_json(stage / "data/members.json", records)
        write_json(stage / "data/source-files.json", source_hashes)
        report = {"source_commit": COMMIT, "archive": identity,
                  "checkpoint": {"bytes": CHECKPOINT_BYTES, "git_blob_sha1": CHECKPOINT_BLOB, "sha256": sha256(checkpoint)},
                  "member_manifest_sha256": sha256(stage / "data/members.json"),
                  "source_manifest_sha256": sha256(stage / "data/source-files.json"), "validation": validation,
                  "software": {"python": platform.python_version(), "numpy": np.__version__, "requests": requests.__version__},
                  "split_policy": "reuse temporal-head-video-holdout-v1; no test epoch selection",
                  "preprocessing": "raw labels and all feature steps retained; no clamping, widening, dropping or normalization"}
        write_json(stage / "data/preparation.json", report)
        if data.exists() or (root / "preparation.json").exists():
            raise FileExistsError("Preparation target already exists")
        (stage / "data").rename(data)
        os.link(data / "preparation.json", root / "preparation.json")
        print(json.dumps({"event": "preparation_ready", **report}), flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s %(fields)s", defaults={"fields": {}}))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    prepare(parser.parse_args().root)
