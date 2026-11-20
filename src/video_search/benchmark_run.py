"""Private, resumable Charades pilot using the existing application pipeline."""

import argparse
import ast
from contextlib import ExitStack, contextmanager
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import sqlite3
import socket
import subprocess
import tempfile
from threading import Event, Lock, Thread
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import uuid4

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from video_search import analysis, extent, media, store
from video_search.benchmark_budget import BudgetGateway
from video_search.config import Settings
from video_search.evaluation import evaluate, validate_manifest
from video_search.log import configure_logging
from video_search.worker import process_one
from video_search.vlm import EXTENT_PROMPT_VERSION, GEMMA_VERIFICATION_PROMPT_VERSION, VLMError


VERSION = "charades-event-extent-pilot-v1"
CONDITIONS = ("ranked_fixed", "uniform_extent", "extent")
DEVELOPMENT_CONDITIONS = ("extent",)
DEVELOPMENT_CHECKS = 1
EVALUATION_CHECKS = 2
POINT_FREEZE = "context-localization.freeze.json"


class RunError(RuntimeError):
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


@contextmanager
def local_api(settings):
    import uvicorn
    from video_search.api import create_app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning", access_log=False))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    began = time.monotonic()
    try:
        while not server.started:
            if not thread.is_alive() or time.monotonic() - began > 15:
                raise RunError("Private benchmark API did not start")
            time.sleep(.01)
        yield origin
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        if thread.is_alive():
            raise RunError("Private benchmark API did not stop; do not start a second run")


def fixed_ranked(settings, query, candidates, recording_id, max_checks=EVALUATION_CHECKS):
    """Spend the declared check cap in rank order, including after a match."""
    checks = []
    recording = store.get_recording(settings.database_url, recording_id)
    for candidate in candidates[:max_checks]:
        if str(candidate["recording_id"]) != recording_id or candidate["source_status"] != "available":
            raise RunError("Ranked candidate leaves the frozen source scope")
        try:
            checked = analysis.verify(settings, recording, query, candidate["start_seconds"], candidate["end_seconds"], 0)
        except (media.MediaError, VLMError) as exc:
            exc.details["completed_evidence_checks"] = [step["verification"]["id"] for step in checks]
            raise
        checks.append({"candidate": candidate, "verification": checked, "reason": "fixed_ranked_control"})
    attempts = sum(step["verification"]["result"]["_trace"]["http_attempts"] for step in checks)
    return {"policy": "ranked_fixed", "policy_version": "ranked-fixed-cap-v2-points", "checks": checks,
            "budget": {"max_checks": max_checks, "max_frames": 8 * max_checks, "calls": len(checks), "frames": 8 * len(checks),
                       "http_attempts": attempts, "sent_frame_slots": 8 * attempts},
            "status": "match" if any(step["verification"]["result"]["status"] == "match" for step in checks) else "insufficient_evidence",
            "stop_reason": "budget_exhausted" if len(checks) == max_checks else "candidates_exhausted"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_context_cache_change(old_source, new_source):
    """Prove normal response handling and every model request are unchanged."""
    if old_source == new_source:
        return "identical-source"
    old, new = ast.parse(old_source), ast.parse(new_source)
    def method(tree):
        clients = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Client"]
        methods = [node for client in clients for node in client.body
                   if isinstance(node, ast.FunctionDef) and node.name == "inspect_extent"]
        if len(clients) != 1 or len(methods) != 1:
            raise RunError("Cached-response proof requires one Client.inspect_extent method")
        return methods[0]
    previous, current = method(old), method(new)
    conflict = ast.parse("data['query_support'] == 'all' and 'present' not in data['sample_support']", mode="eval").body
    guard = ast.parse("contradictory or (data['query_support'] == 'all' and 'present' not in data['sample_support'])", mode="eval").body
    old_guards = [node for node in previous.body if isinstance(node, ast.If) and ast.dump(node.test) == ast.dump(guard)]
    new_branches = [node for node in current.body if isinstance(node, ast.If) and ast.dump(node.test) == ast.dump(conflict)]
    if len(old_guards) != 1 or len(new_branches) != 1 or current.body[-2] is not new_branches[0]:
        raise RunError("Cached-response compatibility proof has an unexpected guard or branch")
    old_guards[0].test = ast.Name(id="contradictory", ctx=ast.Load())
    current.body.remove(new_branches[0])
    if ast.dump(old) != ast.dump(new):
        raise RunError("VLM requests or normal response handling changed; cached cases cannot be reused")
    return "only-unlocalized-context-branch-changed"


def _save(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Checkpoint differs; preserve it before changing this run: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".part", delete=False) as output:
        temporary = Path(output.name)
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError(f"Concurrent checkpoint differs: {path}")
    finally:
        temporary.unlink()


def load_data(root):
    root = Path(root).resolve(strict=True)
    manifests, hashes = {}, {}
    for split in ("train", "test"):
        raw = (root / f"{split}.manifest.json").read_bytes()
        manifests[split] = json.loads(raw)
        validate_manifest(manifests[split])
        hashes[split] = hashlib.sha256(raw).hexdigest()
    groups = [set(manifest["videos"]) for manifest in manifests.values()]
    if groups[0] & groups[1]:
        raise ValueError("Development and test videos overlap")
    source_hashes = []
    for manifest in manifests.values():
        current = set()
        for video_id, video in manifest["videos"].items():
            relative = video["path"]
            if relative != f"media/{video_id}.mp4":
                raise ValueError("Manifest media path differs from its video ID")
            path = media.source_file(root, relative)
            actual = media.hash_source(path)
            if actual != video["sha256"]:
                raise ValueError("Benchmark source changed since preparation")
            current.add(actual)
        source_hashes.append(current)
    if source_hashes[0] & source_hashes[1]:
        raise ValueError("Development and test source hashes overlap")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    if provenance["media_bytes"] > 1024 ** 3 or provenance["three_policy_three_check_max_calls"] > 1500:
        raise ValueError("Prepared pilot exceeds its approved scope")
    return manifests, hashes, provenance


class Pilot:
    """One private namespace and one durable request budget across all run phases."""

    def __init__(self, settings, data, work=None, limit=1500):
        self.data = Path(data).resolve(strict=True)
        self.work = Path(work).resolve() if work else self.data / "run"
        if not self.work.is_relative_to(self.data) or self.work.is_symlink():
            raise ValueError("Private benchmark output must remain inside its data directory")
        self.manifests, manifest_hashes, self.provenance = load_data(self.data)
        if type(limit) is not int or not 1 <= limit <= 1500:
            raise ValueError("Request cap must be within 1..1500")
        self.upstream = analysis.client(settings)
        if self.provenance["three_policy_three_check_max_calls"] > limit:
            raise ValueError("Request cap cannot fit the frozen full pilot; revise scope before inference")
        namespace = conninfo_to_dict(settings.database_url).get("options", "")
        self.identity_data = {"version": VERSION, "manifests": manifest_hashes,
                              "description_spec": analysis.description_spec(settings),
                              "upstream": self.upstream.endpoint, "base_namespace": namespace,
                              "library": str(self.data / "media")}
        self.identity = _digest(self.identity_data)
        self.schema = "charades_" + self.identity[:24]
        self.base_settings = settings
        self.limit = limit
        _save(self.data / "run-binding.json", {"identity": self.identity,
                                               "work_relative": str(self.work.relative_to(self.data)),
                                               "request_cap": limit})
        self.work.mkdir(parents=True, exist_ok=True)
        _save(self.work / "identity.json", {**self.identity_data, "identity": self.identity,
                                          "schema": self.schema, "request_cap": limit})
        self.stack = ExitStack()
        self.stop = Event()
        self.progress_lock = Lock()
        self.context = {}
        self.progress_error = None

    def __enter__(self):
        try:
            lock = self.stack.enter_context(store._connect(self.base_settings.database_url))
            lock.autocommit = True
            acquired = lock.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (int(self.identity[:15], 16),)).fetchone()["acquired"]
            if not acquired:
                raise RuntimeError("Another process owns this benchmark run")
            with store._connect(self.base_settings.database_url) as conn:
                conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            base = self.base_settings.database_url
            options = conninfo_to_dict(base).get("options", "") + f" -csearch_path={self.schema},public"
            database_url = make_conninfo(base, options=options.strip())
            store.init_db(database_url)
            with store._connect(database_url) as conn:
                actual = conn.execute("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                      "WHERE c.oid=to_regclass('jobs')").fetchone()["nspname"]
            if actual != self.schema:
                raise RuntimeError("Benchmark tables are not isolated; no imports may run")
            self.gateway = self.stack.enter_context(BudgetGateway(self.work / "attempts.sqlite", self.limit,
                                                                  self.identity, self.upstream))
            endpoint = ({"voyager_base_url": self.gateway.base_url, "voyager_api_key": self.gateway.token}
                        if self.base_settings.vision_provider == "gemma" else
                        {"qwen_base_url": self.gateway.base_url, "qwen_api_key": self.gateway.token})
            self.settings = replace(self.base_settings, database_url=database_url, media_root=self.data / "media",
                                    library_id=str(self.data / "media"), upload_write_root=None, upload_read_root=None,
                                    **endpoint)
            store.bind_library(database_url, self.settings.library_identity)
            self.thread = Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(timeout=5)
        self.stack.__exit__(*exc)

    def emit(self, event, **fields):
        record = {"at": datetime.now(timezone.utc).isoformat(), "event": event, **self.context,
                  **fields, "budget": self.gateway.snapshot()}
        with self.progress_lock, (self.work / "progress.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, allow_nan=False) + "\n")

    def _heartbeat(self):
        while not self.stop.wait(15):
            try:
                self.emit("heartbeat")
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.progress_error = exc
                return

    def _check_progress(self):
        if self.progress_error is not None:
            raise RuntimeError("Benchmark progress could not be persisted") from self.progress_error

    def _drain(self, stage):
        completed = 0
        while True:
            self._check_progress()
            failures = [job for job in store.list_jobs(self.settings.database_url, 1000) if job["state"] == "failed"]
            if failures:
                _save(self.work / f"{stage}-failure-{failures[0]['id']}.json", failures[0])
                raise RuntimeError(f"Benchmark job failed: {failures[0]['id']}; inspect its private checkpoint")
            if not process_one(self.settings):
                break
            completed += 1
            self.emit("job_processed", stage=stage, jobs_processed_this_phase=completed)

    def index(self):
        self.context = {"phase": "index"}
        self.emit("phase_started")
        videos = {video: entry for manifest in self.manifests.values() for video, entry in manifest["videos"].items()}
        for video in sorted(videos):
            path = media.source_file(self.settings.media_root, video + ".mp4")
            store.enqueue(self.settings.database_url, path.name, *media.fingerprint(path))
        self._drain("import")
        recordings = store.list_recordings(self.settings.database_url, 1000)
        recording_map = {Path(record["source_path"]).stem: str(record["id"]) for record in recordings}
        if set(recording_map) != set(videos):
            raise RuntimeError("Imported source IDs do not match the frozen pilot")
        _save(self.work / "recording-map.json", recording_map)
        for video in sorted(videos):
            store.enqueue_description(self.settings.database_url, recording_map[video], analysis.description_spec(self.settings))
        self._drain("index")
        builds = store.list_description_builds(self.settings.database_url, limit=1000)
        expected = store._description_key(analysis.description_spec(self.settings))
        builds = [build for build in builds if build["config_key"] == expected]
        if len(builds) != len(videos) or any(build["state"] != "ready" for build in builds):
            raise RuntimeError("Every frozen source must have a ready matching index")
        self.emit("phase_completed", indexed_videos=len(builds),
                  indexed_windows=sum(build["completed_windows"] for build in builds))

    def _ready(self):
        recording_map = json.loads((self.work / "recording-map.json").read_text(encoding="utf-8"))
        videos = {video for manifest in self.manifests.values() for video in manifest["videos"]}
        if set(recording_map) != videos:
            raise RunError("Recording map differs from the frozen media")
        key = store._description_key(analysis.description_spec(self.settings))
        builds = [b for b in store.list_description_builds(self.settings.database_url, limit=1000) if b["config_key"] == key]
        if len(builds) != len(videos) or any(b["state"] != "ready" for b in builds):
            raise RunError("Complete every matching index before query evaluation")
        return recording_map

    def protocol(self):
        self._ready()
        names = ["api.py", "analysis.py", "vlm.py", "frames.py", "media.py", "store.py", "extent.py",
                 "evidence.py", "reranker.py", "text_encoder.py", "evaluation.py", "benchmark_run.py",
                 "benchmark_compare.py", "benchmark_budget.py"]
        sources = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names}
        with store._connect(self.settings.database_url) as conn:
            identities = conn.execute("SELECT DISTINCT payload->'_trace'->>'model' AS model, "
                                      "payload->'_trace'->>'revision' AS revision, "
                                      "payload->'_trace'->>'system_fingerprint' AS fingerprint FROM description_windows").fetchall()
        if len(identities) != 1:
            raise RunError("Index perception identity changed across the pilot", identities=identities)
        from video_search.reranker import SPEC as reranker_spec
        import torch
        import transformers
        ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=10).stdout.decode().splitlines()[0]
        prior_freeze = self.work / "test.freeze.json"
        parent_point = self.work / "point-aware.freeze.json"
        return {"version": VERSION, "run_variant": "point-aware-context-v2",
                "prior_protocol_sha256": hashlib.sha256(prior_freeze.read_bytes()).hexdigest() if prior_freeze.exists() else None,
                "parent_point_protocol_sha256": hashlib.sha256(parent_point.read_bytes()).hexdigest() if parent_point.exists() else None,
                "evaluation_status": "exploratory-after-prior-protocol-exposure" if prior_freeze.exists() or parent_point.exists() else "frozen-before-evaluation",
                "localization_rule": "Context support without a present input sample is an explicit localization abstention; raw judgments are retained.",
                "identity": self.identity, "source_sha256": sources,
                "conditions": CONDITIONS, "development_conditions": DEVELOPMENT_CONDITIONS,
                "development_design": "All development queries validate main extent at one check; all evaluation queries compare all three methods at two checks. Prior protocol exposure is recorded; earlier attempts remain charged.",
                "candidate_limit": 24, "path": "description", "rerank": True,
                "task": "supplied-video temporal grounding", "max_checks": EVALUATION_CHECKS, "max_frame_slots": 8 * EVALUATION_CHECKS,
                "development_max_checks": DEVELOPMENT_CHECKS,
                "verification_prompt": GEMMA_VERIFICATION_PROMPT_VERSION if self.settings.vision_provider == "gemma" else self.upstream.spec["prompt_version"],
                "extent_prompt": EXTENT_PROMPT_VERSION,
                "extent_policy": extent.POLICY_VERSION, "reranker": reranker_spec,
                "perception_identity": identities[0], "condition_order_seed": "charades-paired-order-v1",
                "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                            "transformers": transformers.__version__, "ffmpeg": ffmpeg},
                "target_protocol": "VSLNet max(0,start), min(raw_end,reference_duration); raw labels preserved",
                "prediction_protocol": "Source intervals in model/controller order; points are evidence, not interval hypotheses: remove them before assigning interval ranks; remaining nonzero spans keep relative model/check order. Point-only, partial and null-only answers abstain. No GT merging, clipping or invented duration.",
                "primary_metrics": "R@1 at IoU .3/.5/.7 and mean top1 IoU; legacy TALL R@5 NMS is not reproduced",
                "budget_note": "Evaluation caps at 2 checks/16 slots; development caps at 1/8. Distinct-window exhaustion can reduce actual use; report matched-work cases separately.",
                "model_limit": "Hosted revision is unpinned. Fingerprint equality detects some server changes, not unknown training contamination."}

    def _post(self, origin, path, body):
        params = {"path": path, "body": body}
        request = Request(origin + path, json.dumps(body, allow_nan=False).encode(), {"Content-Type": "application/json"})
        try:
            with self.upstream.opener.open(request, timeout=1800) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise RunError("Private API response exceeded its bound", params=params, status=response.status)
                result = json.loads(raw)
                request_id = response.headers.get("X-Request-ID")
            return result, request_id
        except HTTPError as exc:
            details = {"params": params, "status": exc.code,
                       "response_body": exc.read(65536).decode("utf-8", errors="replace"),
                       "request_id": exc.headers.get("X-Request-ID")}
            exc.close()
            raise RunError("Private benchmark API request failed", **details) from exc
        except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            raise RunError("Private benchmark API transport or JSON failed", params=params,
                           status=None, response_body=str(exc), request_id=None) from exc

    def _retrieval(self, origin, query, recording_id, directory):
        path = directory / "retrieval" / (_digest(query["id"]) + ".json")
        request = {"query": query["query"], "path": "description", "recording_ids": [recording_id], "limit": 24}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["request"] != request:
                raise RunError("Retrieval checkpoint differs from its query")
            return data
        raw, raw_id = self._post(origin, "/search", request)
        ranked, ranked_id = self._post(origin, "/search", {**request, "rerank": True})
        for response in (raw, ranked):
            coverage = response["coverage"]
            if coverage["ready_recordings"] != 1 or coverage["ready_windows"] != coverage["total_windows"]:
                raise RunError("Retrieval coverage is incomplete")
            if any(str(c["recording_id"]) != recording_id or c["source_status"] != "available" for c in response["results"]):
                raise RunError("Retrieved source is unavailable or outside the supplied-video scope")
        key = lambda item: (str(item["recording_id"]), item["start_seconds"], item["end_seconds"])
        if {key(c) for c in raw["results"]} != {key(c) for c in ranked["results"]}:
            raise RunError("Raw and reranked searches did not expose the same candidate pool")
        data = {"request": request, "raw": raw, "reranked": ranked, "request_ids": [raw_id, ranked_id]}
        _save(path, data)
        return data

    def freeze(self):
        protocol = self.protocol()
        directory = self.work / "development" / _digest(protocol)
        expected = len(self.manifests["train"]["queries"]) * len(DEVELOPMENT_CONDITIONS)
        if len(list(directory.glob("cases/*.json"))) != expected:
            raise RunError("Finish the full development grid under this protocol before freezing test settings")
        self.report("train")
        for name, expected in protocol["source_sha256"].items():
            raw = Path(__file__).with_name(name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise RunError("Source changed while freezing the test protocol")
            _save(self.work / "context-localization-frozen-source" / name, raw)
        _save(self.work / POINT_FREEZE, protocol)
        self.emit("test_protocol_frozen", protocol_hash=_digest(protocol))

    def reuse_context_cache(self):
        """Reuse every unaffected parent case with an explicit compatibility audit."""
        from video_search.benchmark_compare import _validate_case
        parent_path = self.work / "point-aware.freeze.json"
        parent = json.loads(parent_path.read_bytes())
        current = self.protocol()
        if parent.get("run_variant") != "point-aware-pilot-v1":
            raise RunError("Cache migration requires the point-aware parent protocol")
        for key in ("identity", "conditions", "development_conditions", "max_checks", "max_frame_slots",
                    "development_max_checks", "candidate_limit", "path", "rerank", "verification_prompt",
                    "extent_prompt", "extent_policy", "reranker", "perception_identity", "condition_order_seed",
                    "runtime", "target_protocol", "prediction_protocol", "prior_protocol_sha256"):
            if _digest(parent[key]) != _digest(current[key]):
                raise RunError("Cached model inputs or evaluation settings changed", field=key)
        snapshots = self.work / "point-aware-frozen-source"
        for name, expected in parent["source_sha256"].items():
            if hashlib.sha256((snapshots / name).read_bytes()).hexdigest() != expected:
                raise RunError("Parent source snapshot changed", source=name)
            if name not in {"vlm.py", "benchmark_run.py"} and current["source_sha256"][name] != expected:
                raise RunError("Inference or scoring code changed outside the compatible fix", source=name)
        mode = validate_context_cache_change((snapshots / "vlm.py").read_bytes(), Path(__file__).with_name("vlm.py").read_bytes())
        previous_runner, current_runner = ast.parse((snapshots / "benchmark_run.py").read_bytes()), ast.parse(Path(__file__).read_bytes())
        for name in ("fixed_ranked", "run_queries", "_retrieval"):
            before = [node for node in ast.walk(previous_runner) if isinstance(node, ast.FunctionDef) and node.name == name]
            after = [node for node in ast.walk(current_runner) if isinstance(node, ast.FunctionDef) and node.name == name]
            if len(before) != 1 or len(after) != 1 or ast.dump(before[0]) != ast.dump(after[0]):
                raise RunError("Benchmark request orchestration changed", function=name)
        proof = {"parent_protocol_hash": _digest(parent), "current_protocol_hash": _digest(current),
                 "mode": mode, "parent_vlm_sha256": parent["source_sha256"]["vlm.py"],
                 "current_vlm_sha256": current["source_sha256"]["vlm.py"],
                 "note": "All copied raw results, timestamps and measured work are unchanged; prior attempts are already charged."}
        counts, before_attempts = {}, self.gateway.attempts_used
        recordings = self._ready()
        for split, phase, conditions, cap in (("train", "development", DEVELOPMENT_CONDITIONS, DEVELOPMENT_CHECKS),
                                               ("test", "test", CONDITIONS, EVALUATION_CHECKS)):
            source = self.work / phase / _digest(parent)
            destination = self.work / phase / _digest(current)
            queries = {str(query["id"]): query for query in self.manifests[split]["queries"]}
            _save(destination / "protocol.json", current)
            counts[phase] = 0
            for path in sorted((source / "cases").glob("*.json")):
                raw = path.read_bytes()
                case = json.loads(raw)
                query = queries.get(str(case["query_id"]))
                if query is None:
                    raise RunError("Parent case query is not in its frozen split")
                if (case["protocol_hash"] != _digest(parent) or case["condition"] not in conditions
                        or case["recording_id"] != recordings[query["scope_video_ids"][0]]
                        or path.name != _digest([case["query_id"], case["condition"]]) + ".json"):
                    raise RunError("Parent case leaves its frozen identity")
                _validate_case(case, query, self.manifests[split]["videos"], cap)
                for step in case["result"]["checks"]:
                    verification = step["verification"]
                    result = verification["result"]
                    saved = store.get_verification(self.settings.database_url, verification["id"])
                    if (not saved or saved["response"] != result or saved["samples"] != verification["samples"]
                            or saved["query"] != query["query"] or str(saved["recording_id"]) != case["recording_id"]
                            or saved["start_seconds"] != verification["inspection_start_seconds"]
                            or saved["end_seconds"] != verification["inspection_end_seconds"]):
                        raise RunError("Cached source check differs from its saved evidence")
                    if ("sample_support" in result and result["query_support"] == "all"
                            and "present" not in result["sample_support"]):
                        raise RunError("A cached case reaches the changed interpretation branch; do not reuse it")
                reused = {**case, "protocol_hash": _digest(current),
                          "cache_reuse": {"parent_protocol_hash": _digest(parent),
                                          "parent_case_sha256": hashlib.sha256(raw).hexdigest(), "proof_sha256": _digest(proof)}}
                _save(destination / "cases" / path.name, reused)
                counts[phase] += 1
            for path in sorted((source / "retrieval").glob("*.json")):
                _save(destination / "retrieval" / path.name, path.read_bytes())
        _save(self.work / "context-cache-migration.json", {**proof, "reused_cases": counts})
        if self.gateway.attempts_used != before_attempts:
            raise RunError("Cache migration unexpectedly sent a model request")
        self.emit("cache_migration_completed", reused_cases=counts, proof_sha256=_digest(proof))

    def run_queries(self, split, query_limit=None):
        recording_map = self._ready()
        protocol = self.protocol()
        protocol_hash = _digest(protocol)
        if split == "test":
            if query_limit is not None:
                raise ValueError("An evaluation run cannot omit queries")
            frozen = json.loads((self.work / POINT_FREEZE).read_text(encoding="utf-8"))
            if _digest(frozen) != protocol_hash:
                raise RunError("Frozen test protocol changed; do not mix predictions or tune on this test")
        queries = self.manifests[split]["queries"]
        if query_limit is not None:
            if type(query_limit) is not int or query_limit < 1:
                raise ValueError("Development query limit must be a positive integer")
            queries = queries[:query_limit]
        conditions = DEVELOPMENT_CONDITIONS if split == "train" else CONDITIONS
        max_checks = DEVELOPMENT_CHECKS if split == "train" else EVALUATION_CHECKS
        phase = "development" if split == "train" else "test"
        directory = self.work / phase / protocol_hash
        _save(directory / "protocol.json", protocol)
        self.context = {"phase": phase, "protocol_hash": protocol_hash, "query_count": len(queries),
                        "case_count": len(queries) * len(conditions)}
        self.emit("phase_started")
        completed = 0
        with local_api(self.settings) as origin:
            for query in queries:
                self._check_progress()
                if len(query["scope_video_ids"]) != 1:
                    raise RunError("Charades pilot requires one supplied video per query")
                video_id = query["scope_video_ids"][0]
                recording_id = recording_map[video_id]
                retrieved = self._retrieval(origin, query, recording_id, directory)
                ordered = sorted(conditions, key=lambda name: _digest(["charades-paired-order-v1", query["id"], name]))
                for condition in ordered:
                    case_key = _digest([query["id"], condition])
                    path = directory / "cases" / (case_key + ".json")
                    if path.exists():
                        saved = json.loads(path.read_text(encoding="utf-8"))
                        if (saved["protocol_hash"] != protocol_hash or saved["query_id"] != query["id"]
                                or saved["condition"] != condition or saved["recording_id"] != recording_id):
                            raise RunError("Saved case does not match its frozen identity")
                        completed += 1
                        continue
                    began, attempts = time.perf_counter(), self.gateway.attempts_used
                    metadata = {"query_id": query["id"], "video_id": video_id, "recording_id": recording_id,
                                "condition": condition, "protocol_hash": protocol_hash,
                                "manifest_sha256": self.identity_data["manifests"][split]}
                    try:
                        candidates = copy.deepcopy(retrieved["reranked"]["results"])
                        if condition == "ranked_fixed":
                            result = fixed_ranked(self.settings, query["query"], candidates, recording_id, max_checks)
                        else:
                            result = extent.check_candidates(self.settings, query["query"], candidates, max_checks=max_checks,
                                                             policy=condition, spend_budget=True)
                        fingerprints = {step["verification"]["result"]["_trace"].get("system_fingerprint") for step in result["checks"]}
                        if fingerprints - {protocol["perception_identity"]["fingerprint"]}:
                            raise RunError("Hosted fingerprint changed after protocol freeze", fingerprints=list(fingerprints))
                        used = self.gateway.attempts_used - attempts
                        if used != result["budget"]["http_attempts"]:
                            raise RunError("Case accounting differs from the durable external-attempt ledger")
                        _save(path, {**metadata, "result": result, "http_attempts": used,
                                     "elapsed_seconds": time.perf_counter() - began})
                    except (RunError, VLMError, media.MediaError, ValueError) as exc:
                        _save(directory / "errors" / (case_key + "-" + uuid4().hex + ".json"),
                              {**metadata, "error_type": type(exc).__name__, "error": str(exc),
                               "details": getattr(exc, "details", {}), "http_attempts": self.gateway.attempts_used - attempts})
                        self.emit("case_failed", condition=condition, completed_cases=completed)
                        raise
                    completed += 1
                    self.emit("case_completed", condition=condition, completed_cases=completed)
        self.emit("phase_completed", completed_cases=completed)

    def report(self, split):
        from video_search.benchmark_compare import summarize
        protocol = self.protocol()
        directory = self.work / ("development" if split == "train" else "test") / _digest(protocol)
        cases = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("cases/*.json"))]
        report = summarize(self.manifests[split], cases,
                           conditions=DEVELOPMENT_CONDITIONS if split == "train" else CONDITIONS,
                           max_checks=DEVELOPMENT_CHECKS if split == "train" else EVALUATION_CHECKS)
        retrieval_reports, retrieval_private = {}, {}
        for method in ("raw", "reranked"):
            predictions = []
            for query in self.manifests[split]["queries"]:
                data = json.loads((directory / "retrieval" / (_digest(query["id"]) + ".json")).read_text(encoding="utf-8"))
                video = query["scope_video_ids"][0]
                recording = data["request"]["recording_ids"][0]
                candidates = data[method]["results"]
                if any(str(candidate["recording_id"]) != recording for candidate in candidates):
                    raise RunError("Saved retrieval leaves its supplied-video scope")
                predictions.append({"query_id": query["id"], "candidates": [
                    {"video_id": video, "start_seconds": candidate["start_seconds"],
                     "end_seconds": candidate["end_seconds"], "score": 1 / rank}
                    for rank, candidate in enumerate(candidates, 1)]})
            measured = evaluate(self.manifests[split], predictions)
            retrieval_reports[method] = {"query_count": len(predictions), "mIoU_percent": 100 * measured["mean_top1_iou"],
                                         "R1_percent": {str(t): 100 * measured["metrics"][f"R@1/IoU={t}"] for t in (.3, .5, .7)},
                                         "note": "Retrieval only, before source checks. Same candidate pool; offline index cost is separate."}
            retrieval_private[method] = measured["per_query"]
        report["aggregate"]["retrieval"] = retrieval_reports
        _save(directory / "aggregate.json", {"protocol": protocol, "results": report["aggregate"]})
        _save(directory / "per-query.json", report["private_per_query"])
        _save(directory / "retrieval-per-query.json", retrieval_private)
        snapshot = self.gateway.snapshot()
        _save(self.work / "budget-snapshots" / (str(snapshot["attempts_used"]) + "-" + _digest(snapshot)[:16] + ".json"), snapshot)
        self.emit("report_completed", report_split=split)
        return report["aggregate"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--phase", choices=["index", "development", "reuse-context-cache", "freeze", "test", "report"], required=True)
    parser.add_argument("--query-limit", type=int, help="Development smoke only; held-out test always includes every query")
    parser.add_argument("--report-split", choices=["train", "test"], default="test")
    parser.add_argument("--max-attempts", type=int, default=1500)
    args = parser.parse_args()
    if args.query_limit is not None and args.phase != "development":
        parser.error("--query-limit is only available for development smoke checks")
    configure_logging()
    with Pilot(Settings.from_env(), args.data, args.work, args.max_attempts) as pilot:
        if args.phase == "index":
            pilot.index()
        elif args.phase in {"development", "test"}:
            pilot.run_queries("train" if args.phase == "development" else "test", args.query_limit)
        elif args.phase == "freeze":
            pilot.freeze()
        elif args.phase == "reuse-context-cache":
            pilot.reuse_context_cache()
        else:
            result = pilot.report(args.report_split)
            print(json.dumps({"results": result}))
        print(json.dumps({"phase": args.phase, "schema": pilot.schema, "budget": pilot.gateway.snapshot()}))


if __name__ == "__main__":
    main()
