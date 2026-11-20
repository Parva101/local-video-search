"""Private, resumable request accounting for bounded benchmark runs."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import secrets
import sqlite3
from threading import Thread
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request
from uuid import uuid4


MAX_REQUEST = 5 * 1024 * 1024
MAX_RESPONSE = 1024 * 1024
VERSION = "local-video-search-request-budget-v1"
logger = logging.getLogger("video_search")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _invalid_constant(value):
    raise ValueError("Non-finite JSON number")


class BudgetGateway:
    """Count each external attempt before sending it; never refund a reservation."""

    def __init__(self, ledger_path, limit, identity, upstream_client):
        if type(limit) is not int or not 1 <= limit <= 1500 or not isinstance(identity, str) or not identity.strip():
            raise ValueError("Budget needs a frozen identity and an integer limit within 1..1500")
        self.ledger_path = Path(ledger_path)
        self.limit, self.identity, self.upstream = limit, identity, upstream_client
        self.token = secrets.token_urlsafe(32)
        self.server = self.thread = None
        if self.ledger_path.is_symlink():
            raise ValueError("Budget ledger must not be a link")
        if self.ledger_path.exists():
            try:
                with closing(sqlite3.connect(self.ledger_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                    row = conn.execute("SELECT version, identity, request_limit FROM budget_meta WHERE singleton=1").fetchone()
            except sqlite3.Error as exc:
                raise ValueError("Existing file is not a benchmark budget ledger") from exc
            if row != (VERSION, identity, limit):
                raise ValueError("Budget ledger version, identity or limit differs from this run")
        else:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.ledger_path)) as conn, conn:
                conn.execute("CREATE TABLE budget_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL, identity TEXT NOT NULL, request_limit INTEGER NOT NULL)")
                conn.execute("INSERT INTO budget_meta VALUES (1,?,?,?)", (VERSION, identity, limit))
                conn.execute("""CREATE TABLE attempts (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, params TEXT NOT NULL, started_at TEXT NOT NULL,
                    finished_at TEXT, status INTEGER, gateway_status INTEGER, response_body TEXT,
                    response_sha256 TEXT, upstream_request_id TEXT, gateway_request_id TEXT,
                    usage TEXT, usage_error TEXT, elapsed_seconds REAL, error TEXT)""")

    def __enter__(self):
        if self.server is not None:
            raise RuntimeError("Budget gateway is already running")
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                gateway._handle(self)

            def do_GET(self):
                gateway._send(self, 405, {"code": "method_not_allowed"}, str(uuid4()))

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = self.thread = None

    @property
    def attempts_used(self):
        with closing(sqlite3.connect(self.ledger_path)) as conn:
            return conn.execute("SELECT count(*) FROM attempts").fetchone()[0]

    def snapshot(self):
        with closing(sqlite3.connect(self.ledger_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT status, finished_at, usage, elapsed_seconds FROM attempts").fetchall()
        statuses = {}
        prompt_tokens = completion_tokens = reported = 0
        for row in rows:
            name = str(row["status"]) if row["status"] is not None else "unknown"
            statuses[name] = statuses.get(name, 0) + 1
            if row["usage"] is not None:
                usage = json.loads(row["usage"])
                if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
                    prompt_tokens += usage["prompt_tokens"]
                    completion_tokens += usage["completion_tokens"]
                    reported += 1
        return {"identity": self.identity, "limit": self.limit, "attempts_used": len(rows),
                "remaining": self.limit - len(rows), "pending_attempts": sum(row["finished_at"] is None for row in rows),
                "status_counts": statuses, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                "usage_reported_attempts": reported,
                "elapsed_seconds_sum": sum(row["elapsed_seconds"] or 0 for row in rows),
                "usage_note": "Provider usage is reported only when supplied; unknown or failed-attempt compute is not estimated."}

    def _reserve(self, request_id, digest, params):
        with closing(sqlite3.connect(self.ledger_path, timeout=30)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT count(*) FROM attempts").fetchone()[0] >= self.limit:
                conn.rollback()
                return None
            cursor = conn.execute("INSERT INTO attempts (request_id,request_sha256,params,started_at) VALUES (?,?,?,?)",
                                  (request_id, digest, json.dumps(params, allow_nan=False), _now()))
            conn.commit()
            return cursor.lastrowid

    def _clean_text(self, text):
        return self.upstream._clean(text).replace(self.token, "[redacted]")

    def _clean_bytes(self, body):
        for secret in (self.upstream.api_key, self.token):
            if secret:
                body = body.replace(secret.encode(), b"[redacted]")
        return body

    def _send(self, handler, status, body, request_id, upstream_id=None, gateway_id=None):
        if isinstance(body, dict):
            body = {"status": status, "request_id": request_id, "params": {}, **body}
        data = json.dumps(body, allow_nan=False).encode() if isinstance(body, dict) else body
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("X-Request-ID", upstream_id or request_id)
        if gateway_id:
            handler.send_header("x-obleth-request-id", gateway_id)
        handler.end_headers()
        try:
            handler.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError) as exc:
            logger.warning("benchmark_response_disconnected", extra={"fields": {
                "request_id": request_id, "status": status, "error_type": type(exc).__name__}})

    def _handle(self, handler):
        handler.connection.settimeout(30)
        request_id = self._clean_text(handler.headers.get("X-Request-ID", str(uuid4())))[:200]
        if handler.path != "/v1/chat/completions":
            return self._send(handler, 404, {"code": "unknown_benchmark_path"}, request_id)
        if not hmac.compare_digest(handler.headers.get("Authorization", "").encode(), ("Bearer " + self.token).encode()):
            return self._send(handler, 401, {"code": "benchmark_gateway_unauthorized"}, request_id)
        try:
            length = int(handler.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST:
                return self._send(handler, 413, {"code": "benchmark_request_too_large", "status": 413,
                                               "request_id": request_id}, request_id)
            raw = handler.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Request body is incomplete")
            body = json.loads(raw, parse_constant=_invalid_constant)
            if not isinstance(body, dict) or body.get("model") != self.upstream.model_id:
                raise ValueError("Request model differs from the frozen upstream model")
            messages = body.get("messages")
            if not isinstance(messages, list):
                raise ValueError("Request messages must be a list")
            task = body.get("response_format", {}).get("json_schema", {}).get("name")
            if not isinstance(task, str) or not 1 <= len(task) <= 100:
                raise ValueError("Request needs a bounded task name")
            count = 0
            for message in messages:
                if not isinstance(message, dict) or not isinstance(message.get("content"), list):
                    raise ValueError("Request content must be a list")
                count += sum(isinstance(item, dict) and item.get("type") == "image_url" for item in message["content"])
            params = {"model": self.upstream.model_id, "task": task, "frame_count": count}
        except (ValueError, UnicodeDecodeError, AttributeError, TimeoutError) as exc:
            return self._send(handler, 400, {"code": "invalid_benchmark_request", "status": 400,
                                           "request_id": request_id, "message": self._clean_text(str(exc))}, request_id)
        try:
            seq = self._reserve(request_id, hashlib.sha256(raw).hexdigest(), params)
        except sqlite3.Error as exc:
            logger.error("benchmark_ledger_failed", extra={"fields": {"request_id": request_id,
                         "params": params, "error_type": type(exc).__name__}})
            return self._send(handler, 503, {"code": "benchmark_ledger_failed", "status": 503,
                                           "params": params, "request_id": request_id}, request_id)
        if seq is None:
            return self._send(handler, 409, {"code": "benchmark_budget_exhausted", "status": 409,
                                           "params": params, "request_id": request_id}, request_id)
        self._forward(handler, seq, raw, params, request_id)

    def _forward(self, handler, seq, raw, params, request_id):
        headers = {"Content-Type": "application/json", "X-Request-ID": request_id}
        if self.upstream.api_key:
            headers["Authorization"] = "Bearer " + self.upstream.api_key
        if self.upstream.provider == "gemma":
            headers["x-obleth-boons"] = "off"
        request = Request(self.upstream.endpoint, raw, headers)
        started, status, upstream_id, gateway_id, error = time.perf_counter(), None, None, None, None
        try:
            try:
                response = self.upstream.opener.open(request, timeout=self.upstream.timeout)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.status
                upstream_id = self._clean_text(response.headers.get("X-Request-ID", "")) or None
                gateway_id = self._clean_text(response.headers.get("x-obleth-request-id", "")) or None
                reply = response.read(MAX_RESPONSE + 1)
                declared = response.headers.get("Content-Length")
                if declared is not None and len(reply) <= MAX_RESPONSE:
                    if not declared.isdecimal():
                        raise ValueError("Upstream Content-Length is invalid")
                    if int(declared) != len(reply):
                        raise IncompleteRead(reply, max(0, int(declared) - len(reply)))
            gateway_status = status
            if len(reply) > MAX_RESPONSE:
                error, gateway_status = "response_too_large", 413
                reply = json.dumps({"code": "benchmark_upstream_response_too_large", "status": status,
                                    "params": params, "request_id": request_id,
                                    "response_prefix": self._clean_bytes(reply[:4096]).decode("utf-8", errors="backslashreplace")}).encode()
        except (URLError, TimeoutError, ConnectionError, IncompleteRead, ValueError) as exc:
            error, gateway_status = type(exc).__name__, 502
            details = {"code": "benchmark_upstream_transport_error", "status": status,
                       "params": params, "request_id": request_id, "message": self._clean_text(str(exc))}
            if isinstance(exc, IncompleteRead):
                details.update(received_bytes=len(exc.partial),
                               response_prefix=self._clean_bytes(exc.partial[:4096]).decode("utf-8", errors="backslashreplace"),
                               received_sha256=hashlib.sha256(exc.partial).hexdigest())
            reply = json.dumps(details).encode()
            logger.warning("benchmark_upstream_failed", extra={"fields": {
                "params": params, "request_id": request_id, "status": status, "error_type": error}})
        reply = self._clean_bytes(reply)
        usage, usage_error = None, None
        try:
            parsed = json.loads(reply, parse_constant=_invalid_constant)
            if isinstance(parsed, dict) and isinstance(parsed.get("usage"), dict):
                usage = json.dumps(parsed["usage"], allow_nan=False)
        except (ValueError, UnicodeDecodeError) as exc:
            usage_error = type(exc).__name__
        elapsed = time.perf_counter() - started
        try:
            with closing(sqlite3.connect(self.ledger_path, timeout=30)) as conn, conn:
                conn.execute("""UPDATE attempts SET finished_at=?, status=?, gateway_status=?, response_body=?,
                    response_sha256=?, upstream_request_id=?, gateway_request_id=?, usage=?, usage_error=?,
                    elapsed_seconds=?, error=? WHERE seq=?""", (_now(), status, gateway_status,
                    reply.decode("utf-8", errors="backslashreplace"), hashlib.sha256(reply).hexdigest(),
                    upstream_id, gateway_id, usage, usage_error, elapsed, error, seq))
        except sqlite3.Error as exc:
            logger.error("benchmark_ledger_finish_failed", extra={"fields": {
                "request_id": request_id, "params": params, "status": status, "error_type": type(exc).__name__}})
            return self._send(handler, 503, {"code": "benchmark_ledger_finish_failed", "params": params}, request_id)
        logger.info("benchmark_attempt_completed", extra={"fields": {"seq": seq, "params": params,
                    "request_id": request_id, "status": status, "gateway_status": gateway_status,
                    "upstream_request_id": upstream_id, "gateway_request_id": gateway_id,
                    "elapsed_seconds": elapsed, "error_type": error}})
        self._send(handler, gateway_status, reply, request_id, upstream_id, gateway_id)
