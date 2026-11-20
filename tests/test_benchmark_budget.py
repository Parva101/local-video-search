from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import sqlite3
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from video_search.benchmark_budget import BudgetGateway, MAX_REQUEST, MAX_RESPONSE
from video_search.vlm import Client, VLMError
from test_vlm import endpoint, envelope, frames


def post(gateway, body=None, *, token=None, path="/v1/chat/completions"):
    payload = {"model": gateway.upstream.model_id, "messages": [],
               "response_format": {"json_schema": {"name": "verify"}}} if body is None else body
    request = Request(gateway.base_url.removesuffix("/v1") + path, json.dumps(payload).encode(),
                      {"Content-Type": "application/json", "Authorization": "Bearer " + (gateway.token if token is None else token),
                       "X-Request-ID": "same-request"})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def rows(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM attempts ORDER BY seq")]


def test_retries_are_separate_durable_attempts_and_preserve_provider_ids(tmp_path):
    image, samples = frames()
    with endpoint([(500, {"error": "busy"}), (429, {"error": "busy"}), (200, envelope())],
                  gateway_id="provider-gateway") as (url, upstream_calls):
        upstream = Client(url, "upstream-secret")
        path = tmp_path / "calls.sqlite"
        with BudgetGateway(path, 3, "frozen-run", upstream) as gateway:
            result = Client(gateway.base_url, gateway.token).describe(image, samples, 10, 12)
            assert gateway.attempts_used == 3
            assert result["_trace"]["http_attempts"] == 3
            assert result["_trace"]["upstream_request_id"] == "upstream-test-id"
            assert result["_trace"]["gateway_request_id"] == "provider-gateway"
            assert len(upstream_calls) == 3
            assert [row["status"] for row in rows(path)] == [500, 429, 200]
            assert all(row["finished_at"] for row in rows(path))
            assert len({row["request_id"] for row in rows(path)}) == 1
            assert gateway.snapshot()["completion_tokens"] == 10
        with BudgetGateway(path, 3, "frozen-run", upstream) as resumed:
            assert resumed.attempts_used == 3
            assert post(resumed)[0] == 409
        assert len(upstream_calls) == 3


def test_cap_counts_attempts_not_successes(tmp_path):
    image, samples = frames()
    with endpoint([(500, {"error": "busy"})]) as (url, history):
        with BudgetGateway(tmp_path / "calls.sqlite", 2, "run", Client(url)) as gateway:
            with pytest.raises(VLMError) as caught:
                Client(gateway.base_url, gateway.token).describe(image, samples, 10, 12)
            assert caught.value.details["status"] == 409
            assert "benchmark_budget_exhausted" in caught.value.details["response_body"]
            assert gateway.attempts_used == len(history) == 2


def test_concurrent_requests_cannot_exceed_cap(tmp_path):
    with endpoint([(200, envelope())]) as (url, history):
        with BudgetGateway(tmp_path / "calls.sqlite", 3, "run", Client(url)) as gateway:
            with ThreadPoolExecutor(max_workers=8) as pool:
                statuses = list(pool.map(lambda _: post(gateway)[0], range(8)))
            assert statuses.count(200) == len(history) == gateway.attempts_used == 3
            assert statuses.count(409) == 5


@pytest.mark.parametrize("changed", [{"limit": 3}, {"identity": "another"}])
def test_resume_cannot_change_frozen_identity_or_limit(tmp_path, changed):
    path = tmp_path / "calls.sqlite"
    with endpoint([(200, envelope())]) as (url, history):
        upstream = Client(url)
        with BudgetGateway(path, 2, "run", upstream) as gateway:
            assert post(gateway)[0] == 200
        with pytest.raises(ValueError, match="identity|limit"):
            BudgetGateway(path, changed.get("limit", 2), changed.get("identity", "run"), upstream)
        assert len(history) == 1


def test_unfinished_reservation_still_consumes_budget(tmp_path):
    path = tmp_path / "calls.sqlite"
    with endpoint([(200, envelope())]) as (url, history):
        with BudgetGateway(path, 1, "run", Client(url)) as gateway:
            gateway._reserve("abandoned", "a" * 64, {"model": gateway.upstream.model_id, "task": "verify", "frame_count": 8})
        with BudgetGateway(path, 1, "run", Client(url)) as resumed:
            assert resumed.attempts_used == 1
            assert resumed.snapshot()["pending_attempts"] == 1
            assert post(resumed)[0] == 409
        assert history == []


def test_secrets_are_removed_from_reply_and_ledger_not_forwarded_auth(tmp_path):
    secret = "upstream-secret"
    path = tmp_path / "calls.sqlite"
    with endpoint([(400, {"error": secret})], upstream_id=secret, gateway_id=secret) as (url, history):
        with BudgetGateway(path, 1, "run", Client(url, secret)) as gateway:
            status, body, headers = post(gateway)
            assert status == 400 and secret.encode() not in body
            assert secret not in str(headers) + str(rows(path))
            assert gateway.token not in str(rows(path))
            assert history[0]["headers"]["Authorization"] == "Bearer " + secret
            assert b"[redacted]" in body


@pytest.mark.parametrize("options,status", [({"token": "wrong"}, 401), ({"path": "/other"}, 404),
                                           ({"body": {"model": "other"}}, 400), ({"body": []}, 400)])
def test_invalid_requests_do_not_spend_budget(tmp_path, options, status):
    with endpoint([(200, envelope())]) as (url, history):
        with BudgetGateway(tmp_path / "calls.sqlite", 1, "run", Client(url)) as gateway:
            assert post(gateway, **options)[0] == status
            assert gateway.attempts_used == 0
        assert history == []


def test_redirects_are_never_followed(tmp_path):
    with endpoint([(200, envelope())]) as (destination, destination_calls):
        with endpoint([(302, {"error": "redirect"})], redirect_to=destination) as (url, history):
            with BudgetGateway(tmp_path / "calls.sqlite", 1, "run", Client(url, "secret")) as gateway:
                assert post(gateway)[0] == 302
                assert gateway.attempts_used == len(history) == 1
        assert destination_calls == []


def test_request_and_response_bounds_fail_explicitly(tmp_path):
    with endpoint([(200, b"x" * (MAX_RESPONSE + 1))]) as (url, history):
        with BudgetGateway(tmp_path / "calls.sqlite", 2, "run", Client(url)) as gateway:
            address = urlsplit(gateway.base_url)
            conn = HTTPConnection(address.hostname, address.port, timeout=5)
            conn.putrequest("POST", "/v1/chat/completions")
            conn.putheader("Authorization", "Bearer " + gateway.token)
            conn.putheader("Content-Length", str(MAX_REQUEST + 1))
            conn.endheaders()
            response = conn.getresponse()
            assert response.status == 413
            response.read()
            conn.close()
            assert gateway.attempts_used == 0
            status, body, _ = post(gateway)
            assert status == 413 and b"response_too_large" in body
            assert gateway.attempts_used == len(history) == 1


def test_malformed_provider_reply_is_preserved_and_counted(tmp_path):
    path = tmp_path / "calls.sqlite"
    with endpoint([(200, b"not-json\xff")]) as (url, history):
        with BudgetGateway(path, 1, "run", Client(url)) as gateway:
            assert post(gateway)[1] == b"not-json\xff"
            assert gateway.attempts_used == len(history) == 1
            assert rows(path)[0]["usage_error"] == "UnicodeDecodeError"


def test_truncated_provider_body_is_an_explicit_counted_error(tmp_path):
    class Truncated(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"partial-upstream-secret")

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Truncated)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        path = tmp_path / "calls.sqlite"
        upstream = Client(f"http://127.0.0.1:{server.server_port}/v1", "upstream-secret")
        with BudgetGateway(path, 1, "run", upstream) as gateway:
            status, raw, _ = post(gateway)
            body = json.loads(raw)
            assert status == 502 and body["code"] == "benchmark_upstream_transport_error"
            assert body["response_prefix"] == "partial-[redacted]"
            assert rows(path)[0]["status"] == 200
            assert rows(path)[0]["error"] == "IncompleteRead"
            assert gateway.attempts_used == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_refused_connection_consumes_a_reservation(tmp_path):
    with socket.socket() as blocked:
        blocked.bind(("127.0.0.1", 0))
        port = blocked.getsockname()[1]
        path = tmp_path / "calls.sqlite"
        with BudgetGateway(path, 1, "run", Client(f"http://127.0.0.1:{port}/v1")) as gateway:
            status, body, _ = post(gateway)
            assert status == 502 and b"benchmark_upstream_transport_error" in body
            assert rows(path)[0]["status"] is None
            assert gateway.attempts_used == 1


@pytest.mark.parametrize("limit", [0, True, 1501])
def test_invalid_limits_do_not_create_a_ledger(tmp_path, limit):
    path = tmp_path / "calls.sqlite"
    with pytest.raises(ValueError):
        BudgetGateway(path, limit, "run", Client("http://localhost:1/v1"))
    assert not path.exists()


def test_unrelated_sqlite_file_is_not_modified(tmp_path):
    path = tmp_path / "other.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE important (value text)")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="budget ledger"):
        BudgetGateway(path, 1, "run", Client("http://localhost:1/v1"))
    assert path.read_bytes() == before


def test_corrupt_ledger_stops_before_forwarding(tmp_path):
    path = tmp_path / "calls.sqlite"
    with endpoint([(200, envelope())]) as (url, history):
        with BudgetGateway(path, 1, "run", Client(url)) as gateway:
            with sqlite3.connect(path) as conn:
                conn.execute("DROP TABLE attempts")
            status, body, _ = post(gateway)
            assert status == 503 and b"benchmark_ledger_failed" in body
        assert history == []
