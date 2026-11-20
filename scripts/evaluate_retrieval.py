"""Score saved predictions, or collect local /search output using frozen labels.

Example:
  python scripts/evaluate_retrieval.py --manifest evaluation/qvhighlights-public-example.json \
    --recording-map recording-map.json --output run.json --qv-export submission.jsonl

The recording map is {external_video_id: local_recording_uuid}. Use --task corpus
to search every mapped video; supplied_video uses each query's explicit scope.
No label intervals are sent to the search API. Official mAP must use the dataset
author's evaluator. Output files are exclusive-create to protect previous runs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from video_search.evaluation import evaluate, qvhighlights_rows, search_requests


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--predictions", type=Path, help="JSON list, or a previous run containing predictions")
    source.add_argument("--recording-map", type=Path)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--path", choices=("visual", "description", "hybrid"), default="description")
    parser.add_argument("--rerank", action="store_true", help="Rerank live description-search candidates")
    parser.add_argument("--task", choices=("supplied_video", "corpus"), default="supplied_video")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--qv-export", type=Path)
    args = parser.parse_args()
    if args.rerank and args.path != "description":
        parser.error("--rerank requires --path description")
    if args.rerank and args.predictions:
        parser.error("--rerank requires live search with --recording-map")
    if args.qv_export is not None and args.output.resolve() == args.qv_export.resolve():
        parser.error("Report and official-format export need different output paths")
    for output in (args.output, args.qv_export):
        if output is not None and output.exists():
            parser.error(f"Output already exists: {output}")
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    responses = []
    if args.predictions:
        saved = json.loads(args.predictions.read_text(encoding="utf-8"))
        predictions = saved["predictions"] if isinstance(saved, dict) else saved
    else:
        endpoint = urlsplit(args.api)
        if (endpoint.scheme not in {"http", "https"} or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path not in {"", "/"}):
            parser.error("--api must be a local HTTP(S) origin without credentials or a path")
        recording_map = json.loads(args.recording_map.read_text(encoding="utf-8"))
        reverse_map = {value: key for key, value in recording_map.items()}
        requests = search_requests(manifest, recording_map, args.path, args.limit, args.task)
        opener = build_opener(ProxyHandler({}), NoRedirect())
        predictions = []
        for query_id, body in requests:
            if args.rerank:
                body["rerank"] = True
            request = Request(args.api.rstrip("/") + "/search", json.dumps(body).encode(), {"Content-Type": "application/json"})
            began = time.perf_counter()
            for attempt in range(3):
                try:
                    with opener.open(request, timeout=600) as response:
                        result = json.load(response)
                        request_id = response.headers.get("X-Request-ID")
                    break
                except (HTTPError, URLError, TimeoutError) as exc:
                    details = {"query_id": query_id, "params": body, "attempt": attempt + 1,
                               "status": getattr(exc, "code", None), "error_type": type(exc).__name__}
                    if isinstance(exc, HTTPError):
                        details.update(response_body=exc.read(65536).decode("utf-8", errors="replace"),
                                       request_id=exc.headers.get("X-Request-ID"))
                    if attempt == 2 or (isinstance(exc, HTTPError) and exc.code != 429 and exc.code < 500):
                        exc.add_note(json.dumps(details))
                        raise
                    logging.getLogger("video_search").warning("evaluation_search_retry", extra={"fields": details})
                    time.sleep(.5 * 2 ** attempt)
            coverage = result["coverage"]
            branches = coverage.values() if args.path == "hybrid" else [coverage]
            if any(c["ready_windows"] != c["total_windows"] or c["ready_recordings"] != c["total_recordings"]
                   or c["total_recordings"] != len(body["recording_ids"]) for c in branches):
                raise RuntimeError(f"Incomplete index coverage for query {query_id}; finish every selected index before evaluation")
            for candidate in result["results"]:
                if candidate.get("source_status") != "available":
                    raise RuntimeError(f"Source is not available for query {query_id}, recording {candidate['recording_id']}: "
                                       f"{candidate.get('source_status')}; request_id={request_id}")
            candidates = [{"video_id": reverse_map[c["recording_id"]], "start_seconds": c["start_seconds"],
                           "end_seconds": c["end_seconds"], "score": 1 / rank}
                          for rank, c in enumerate(result["results"], 1)]
            predictions.append({"query_id": query_id, "candidates": candidates, "elapsed_seconds": time.perf_counter() - began,
                                "calls": 0, "frames": 0})
            responses.append({"query_id": query_id, "request": body, "request_id": request_id, "response": result})
    report = evaluate(manifest, predictions)
    exported = qvhighlights_rows(manifest, predictions) if args.qv_export else None
    output = {"created_at": datetime.now(timezone.utc).isoformat(), "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "task": args.task if not args.predictions else "saved-predictions", "path": args.path if not args.predictions else None,
              "rerank": args.rerank if not args.predictions else None,
              "cost_note": "Live search calls/frames count online vision checks only; offline index cost is not included.",
              "predictions": predictions, "report": report, "responses": responses}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, allow_nan=False)
        handle.write("\n")
    if exported is not None:
        with args.qv_export.open("x", encoding="utf-8") as handle:
            for row in exported:
                handle.write(json.dumps(row, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "rerank": output["rerank"], "metrics": report["metrics"], "queries": report["counts"]["queries"]}))


if __name__ == "__main__":
    main()
