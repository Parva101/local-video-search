"""Fetch the pinned UniVTG research release into private Sol storage."""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time


UPSTREAM_COMMIT = "32659ac7aeba21742a63274f30eba785fc57e247"
ARTIFACTS = {
    "charades_train.jsonl": ("1Ywo5A7wpdMfI9Ph9XllCMKi2PC-YJZZ9", "cc061d290f5be0735ecfaf80d9f9d09a5032f8b95faef114fe6ce21add2df9aa"),
    "charades_test.jsonl": ("1Z6pElW_Gq-LeIlD-ptnyf7G6NeYE1FYW", "fbf26493b5b1b7c08e3cb0b79e3ef400709229205cfea24745798292ba7eb7d6"),
    "opt.json": ("1CBHPMvq2_nBWG7eAw9mIhYJbTLZan0kd", "2957f39e3d94448758945214402e8056046196258e5bc4f14602fe519c389519"),
    "model_best.ckpt": ("1rXxBhjsEvHYywvf--RIFMWJ1VV2ZdblX", None),
    "vid_slowfast.tar": ("1JPkrJcpSwJqrGlq-aIW58UgxWRenVPVN", None),
    "vid_clip.tar": ("1JQGEz6jiizAccylBDZoMQQHMDwcQ7Nkv", None),
    "txt_clip.tar": ("1JYXjl0AnKHjDYb4_c-SUp4zq-_pXj_tU", None),
}
logger = logging.getLogger("temporal_prepare")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unpack(archive, destination):
    """Flatten only regular NPZ files; never trust archive paths or links."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    names = set()
    with tarfile.open(archive, "r:*") as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if member.isdir():
                continue
            if not member.isfile() or path.suffix != ".npz" or member.size > 64 * 1024 ** 2:
                raise ValueError(f"Unexpected feature member: {member.name}")
            if path.name in names:
                raise ValueError(f"Duplicate feature name: {path.name}")
            names.add(path.name)
            target = destination / path.name
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError(f"Unreadable feature member: {member.name}")
            with stream:
                if target.exists():
                    digest = hashlib.sha256()
                    while block := stream.read(1024 ** 2):
                        digest.update(block)
                    if target.stat().st_size != member.size or sha256(target) != digest.hexdigest():
                        raise ValueError(f"Existing feature differs: {target}")
                else:
                    partial = target.with_suffix(".part")
                    with partial.open("wb") as output:
                        shutil.copyfileobj(stream, output)
                        output.flush()
                        os.fsync(output.fileno())
                    if partial.stat().st_size != member.size:
                        raise ValueError(f"Incomplete feature: {member.name}")
                    partial.replace(target)
    if not names:
        raise ValueError("Feature archive contains no NPZ files")
    return len(names)


def prepare(root):
    import gdown
    from gdown.exceptions import FileURLRetrievalError
    import requests

    root = Path(root).resolve()
    data, downloads = root / "data", root / "downloads"
    data.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(exist_ok=True)
    provenance_path = data / "artifacts.json"
    provenance = json.loads(provenance_path.read_bytes()) if provenance_path.exists() else {}
    for name, (file_id, expected_hash) in ARTIFACTS.items():
        target = downloads / name
        if not target.exists():
            partial = downloads / (name + ".part")
            for attempt in range(3):
                try:
                    result = gdown.download(id=file_id, output=str(partial), quiet=False,
                                            use_cookies=False, resume=True)
                    if result is None:
                        raise RuntimeError("Google Drive returned no artifact")
                    with partial.open("rb") as stream:
                        prefix = stream.read(256).lower()
                    if b"<html" in prefix or b"<!doctype" in prefix:
                        raise ValueError(f"HTML instead of artifact: {name}")
                    actual_hash = sha256(partial)
                    if expected_hash is not None and actual_hash != expected_hash:
                        raise ValueError(f"Artifact checksum mismatch: {name}")
                    partial.replace(target)
                    break
                except (requests.RequestException, FileURLRetrievalError, RuntimeError) as exc:
                    response = getattr(exc, "response", None)
                    fields = {"artifact": name, "file_id": file_id, "attempt": attempt + 1,
                              "status": response.status_code if response is not None else None,
                              "response_body": response.text[:4096] if response is not None else str(exc),
                              "request_id": response.headers.get("X-Request-ID") if response is not None else None}
                    if attempt == 2:
                        raise RuntimeError(json.dumps(fields)) from exc
                    logger.warning("artifact_download_retry", extra={"fields": fields})
                    time.sleep(2 ** attempt)
        digest = sha256(target)
        if expected_hash is not None and digest != expected_hash:
            raise ValueError(f"Artifact checksum mismatch: {name}")
        if name in provenance and provenance[name]["sha256"] != digest:
            raise ValueError(f"Previously recorded artifact changed: {name}")
        record = {"source": f"https://drive.google.com/file/d/{file_id}/view",
                  "bytes": target.stat().st_size, "sha256": digest,
                  "hash_source": "verified-before-download" if expected_hash else "recorded-first-download"}
        if name.endswith(".tar"):
            record["feature_files"] = unpack(target, data / name.removesuffix(".tar"))
        else:
            published = data / name
            if published.exists():
                if sha256(published) != digest:
                    raise ValueError(f"Published artifact differs: {name}")
            else:
                shutil.copyfile(target, published)
        provenance[name] = record
        temporary = provenance_path.with_suffix(".part")
        temporary.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(provenance_path)
        print(json.dumps({"event": "artifact_ready", "artifact": name, **record}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    prepare(args.root)
