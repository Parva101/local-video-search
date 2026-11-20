import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from threading import Thread

from PIL import Image
import pytest

from video_search.vlm import Client, MODEL_ID, GEMMA_MODEL_ID, GEMMA_SPEC, VLMError, Verification
from video_search import analysis, store
from video_search.config import Settings


DESCRIPTION = {"summary": "A red object is visible.", "actions": [], "objects": ["red object"], "uncertainties": []}


def envelope(content=DESCRIPTION, finish="stop"):
    return {"model": MODEL_ID, "choices": [{"finish_reason": finish, "message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10}}


@contextmanager
def endpoint(responses, upstream_id="upstream-test-id", gateway_id=None, redirect_to=None):
    history = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            history.append({"path": self.path, "headers": dict(self.headers),
                            "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            status, response = responses[min(len(history) - 1, len(responses) - 1)]
            data = response if isinstance(response, bytes) else json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", upstream_id)
            if gateway_id is not None:
                self.send_header("x-obleth-request-id", gateway_id)
            if redirect_to is not None:
                self.send_header("Location", redirect_to)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", history
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def frames():
    return [Image.new("RGB", (1024, 768), "red"), Image.new("RGB", (32, 32), "blue")], [
        {"source_seconds": 10.5}, {"source_seconds": 11.5},
    ]


def extent_frames():
    return [Image.new("RGB", (32, 32), "red") for _ in range(8)], [{"source_seconds": i + .5} for i in range(8)]


def extent_answer(states=None, **changes):
    return {"query_support": "all", "sample_support": states or ["present"] * 8,
            "anchor_relation": "not_applicable", "observation": "A visible action is present.", **changes}


def test_extent_sends_compact_separate_contract_without_changing_existing_specs():
    from video_search.vlm import EXTENT_PROMPT_VERSION
    images, samples = extent_frames()
    before = dict(GEMMA_SPEC)
    with endpoint([(200, envelope(extent_answer()))]) as (url, calls):
        result = Client(url).inspect_extent("visible action", images, samples, 0, 8)
    assert result["_trace"]["prompt_version"] == EXTENT_PROMPT_VERSION
    body = calls[0]["body"]
    assert body["max_tokens"] == 2048
    assert body["response_format"]["json_schema"]["name"] == "extent"
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"query_support", "sample_support", "anchor_relation", "observation"}
    assert schema["properties"]["sample_support"]["minItems"] == schema["properties"]["sample_support"]["maxItems"] == 8
    assert "status" not in schema["properties"]
    assert schema["properties"]["anchor_relation"]["const"] == "not_applicable"
    prompt = body["messages"][0]["content"][0]["text"]
    assert "one line" in prompt and "200 characters" in prompt
    assert '"anchor_relation":"not_applicable"' in prompt
    assert GEMMA_SPEC == before and GEMMA_SPEC["prompt_version"] == "visible-evidence-gemma-json-v2"
    assert len(result["_trace"]["frame_sha256"]) == 8


@pytest.mark.parametrize("changes", [
    {"sample_support": ["present"] * 7},
    {"anchor_relation": "unknown"},
    {"status": "match"},
    {"observation": "x" * 301},
])
def test_extent_rejects_schema_or_context_conflicts(changes):
    images, samples = extent_frames()
    with endpoint([(200, envelope(extent_answer(**changes)))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).inspect_extent("action", images, samples, 0, 8)
    assert error.value.code in {"invalid_vlm_response", "invalid_extent_response"}
    assert len(calls) == 1
    assert error.value.details["request_id"]


def test_extent_reference_does_not_count_as_a_new_match():
    images, samples = extent_frames()
    reply = extent_answer(["present"] + ["absent"] * 7, query_support="partial", anchor_relation="same_event")
    with endpoint([(200, envelope(reply))]) as (url, calls):
        result = Client(url).inspect_extent("action", images, samples, 1, 8, anchor_index=0)
    assert result["status"] == "no_match" and len(calls) == 1


def test_extent_requires_new_samples_inside_the_new_window():
    images, samples = extent_frames()
    with endpoint([(200, envelope(extent_answer()))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).inspect_extent("action", images, samples, 4, 8, anchor_index=0)
    assert error.value.code == "invalid_frames" and not calls


def test_extent_partial_match_is_valid_and_prompt_status_excludes_reference():
    images, samples = extent_frames()
    states = ["present", "absent", "present", "unknown", "unknown", "absent", "absent", "absent"]
    reply = extent_answer(states, query_support="partial", anchor_relation="same_event")
    with endpoint([(200, envelope(reply))]) as (url, calls):
        result = Client(url).inspect_extent("pick up a cup and pour water", images, samples, 1, 8, anchor_index=0)
    assert result["status"] == "match" and result["query_support"] == "partial"
    assert result["sample_support"] == states and len(calls) == 1
    prompt = calls[0]["body"]["messages"][0]["content"][0]["text"]
    assert "with four fields" in prompt and "Do not return a status field" in prompt
    assert 'when "query_support" is "partial"' in prompt
    assert "including the reference frame" in prompt
    assert "Status and intervals use only new samples" in prompt


@pytest.mark.parametrize("states,anchor_index,support,expected", [
    (["absent"] * 7 + ["present"], 7, "partial", "no_match"),
    (["present"] * 8, None, "all", "match"),
    (["unknown"] * 8, None, "unknown", "insufficient_evidence"),
    (["present"] + ["absent"] * 6 + ["unknown"], 0, "unknown", "insufficient_evidence"),
])
def test_extent_v2_derives_status_only_from_new_sample_evidence(states, anchor_index, support, expected, caplog):
    images, samples = extent_frames()
    raw = {"query_support": support, "sample_support": states,
           "anchor_relation": "not_applicable" if anchor_index is None else "same_event", "observation": "Visible sample evidence."}
    start, end = (1, 8) if anchor_index == 0 else (0, 7) if anchor_index == 7 else (0, 8)
    with endpoint([(200, envelope(raw))]) as (url, calls):
        with caplog.at_level("INFO", logger="video_search"):
            result = Client(url).inspect_extent("action", images, samples, start, end, anchor_index)
    assert result["status"] == expected and result["sample_support"] == states
    assert result["_trace"]["prompt_version"] == "source-sample-extent-json-v5"
    assert result["_trace"]["status_derivation"] == "new-sample-support-v1"
    assert result["_trace"]["query_support_scope"] == "all-input-samples-v1"
    logged = next(record.fields for record in caplog.records if record.message == "vlm_response")
    assert set(json.loads(logged["response_body"])) == {"query_support", "sample_support", "anchor_relation", "observation"}
    assert len(calls) == 1


def test_extent_v2_rejects_legacy_status_field_in_model_output():
    images, samples = extent_frames()
    legacy = {"status": "match", "query_support": "all", "sample_support": ["present"] * 8,
              "anchor_relation": "not_applicable", "observation": "Visible action."}
    with endpoint([(200, envelope(legacy))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).inspect_extent("action", images, samples, 0, 8)
    assert error.value.code == "invalid_vlm_response" and len(calls) == 1


@pytest.mark.parametrize("anchor_index", [0, 7])
def test_extent_v5_accepts_reference_only_all_support_without_new_match(anchor_index):
    images, samples = extent_frames()
    states = ["absent"] * 8
    states[anchor_index] = "present"
    raw = {"query_support": "all", "sample_support": states,
           "anchor_relation": "unknown", "observation": "Only the reference shows the action."}
    with endpoint([(200, envelope(raw))]) as (url, calls):
        result = Client(url).inspect_extent("action", images, samples, 1 if anchor_index == 0 else 0,
                                           8 if anchor_index == 0 else 7, anchor_index)
    assert result["status"] == "no_match" and result["query_support"] == "all"
    assert result["sample_support"] == raw["sample_support"] and len(calls) == 1
    assert result["_trace"]["query_support_scope"] == "all-input-samples-v1"


@pytest.mark.parametrize("state", ["absent", "unknown"])
@pytest.mark.parametrize("anchor_index", [None, 7])
def test_extent_unlocalized_context_support_abstains_and_preserves_raw_evidence(state, anchor_index, caplog):
    images, samples = extent_frames()
    raw = extent_answer([state] * 8, query_support="all",
                        anchor_relation="not_applicable" if anchor_index is None else "unknown")
    with endpoint([(200, envelope(raw))]) as (url, calls):
        with caplog.at_level("INFO", logger="video_search"):
            result = Client(url).inspect_extent("action", images, samples, 0, 7 if anchor_index == 7 else 8, anchor_index)
    assert result["status"] == "insufficient_evidence" and len(calls) == 1
    assert {key: result[key] for key in raw} == raw
    assert result["_trace"]["status_derivation"] == "context-unlocalized-abstention-v2"
    assert result["_trace"]["localization_warning"] == "context_support_without_localized_samples"
    logged = next(record.fields for record in caplog.records if record.message == "vlm_response")
    assert json.loads(logged["response_body"]) == raw
    warning = next(record for record in caplog.records if record.message == "extent_localization_abstention")
    assert warning.levelname == "WARNING"
    assert warning.fields["params"]["anchor_index"] == anchor_index
    assert warning.fields["request_id"] == result["_trace"]["request_id"]
    assert warning.fields["upstream_request_id"] == result["_trace"]["upstream_request_id"]
    assert warning.fields["gateway_request_id"] == result["_trace"]["gateway_request_id"]


def test_extent_v2_keeps_duplicate_timestamp_conflict_guard():
    images, samples = extent_frames()
    samples[1] = dict(samples[0])
    raw = {"query_support": "partial", "sample_support": ["present", "absent"] + ["unknown"] * 6,
           "anchor_relation": "not_applicable", "observation": "Conflicting sample claims."}
    with endpoint([(200, envelope(raw))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).inspect_extent("action", images, samples, 0, 8)
    assert error.value.code == "invalid_extent_response" and len(calls) == 1


def test_extent_v2_keeps_reference_role_guard():
    images, samples = extent_frames()
    raw = extent_answer(query_support="partial")
    with endpoint([(200, envelope(raw))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).inspect_extent("action", images, samples, 1, 8, anchor_index=0)
    assert error.value.code == "invalid_vlm_response" and len(calls) == 1
    prompt = calls[0]["body"]["messages"][0]["content"][0]["text"]
    assert 'never use "not_applicable"' in prompt


@pytest.mark.parametrize("reference_state", ["absent", "unknown", "present"])
def test_extent_v4_accepts_unknown_without_a_positive_new_reference_pair(reference_state):
    images, samples = extent_frames()
    states = ["absent"] * 7 + [reference_state]
    raw = extent_answer(states, query_support="unknown", anchor_relation="unknown")
    with endpoint([(200, envelope(raw))]) as (url, calls):
        result = Client(url).inspect_extent("action", images, samples, 0, 7, anchor_index=7)
    assert result["status"] == "no_match" and result["anchor_relation"] == "unknown"
    assert result["sample_support"] == states and len(calls) == 1
    assert result["_trace"]["prompt_version"] == "source-sample-extent-json-v5"
    schema = calls[0]["body"]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["anchor_relation"]["enum"] == ["same_event", "different_event", "unknown"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"query_support", "sample_support", "anchor_relation", "observation"}


@pytest.mark.parametrize("reference_state", ["absent", "unknown"])
def test_extent_v4_accepts_unknown_when_only_new_frames_are_positive(reference_state):
    images, samples = extent_frames()
    states = ["present"] * 7 + [reference_state]
    raw = extent_answer(states, query_support="partial", anchor_relation="unknown")
    with endpoint([(200, envelope(raw))]) as (url, calls):
        result = Client(url).inspect_extent("action", images, samples, 0, 7, anchor_index=7)
    assert result["status"] == "match" and result["anchor_relation"] == "unknown"
    assert result["sample_support"] == states and len(calls) == 1


@pytest.mark.parametrize("relation", ["same_event", "different_event", "unknown"])
def test_extent_v3_preserves_other_raw_relations_when_no_event_pair_exists(relation):
    images, samples = extent_frames()
    raw = extent_answer(["absent"] * 8, query_support="unknown", anchor_relation=relation)
    with endpoint([(200, envelope(raw))]) as (url, calls):
        result = Client(url).inspect_extent("action", images, samples, 0, 7, anchor_index=7)
    assert result["status"] == "no_match" and result["anchor_relation"] == relation
    assert len(calls) == 1


def test_extent_v3_keeps_unknown_relation_for_a_positive_pair():
    images, samples = extent_frames()
    raw = extent_answer(query_support="partial", anchor_relation="unknown")
    with endpoint([(200, envelope(raw))]) as (url, calls):
        result = Client(url).inspect_extent("action", images, samples, 1, 8, anchor_index=0)
    assert result["status"] == "match" and result["anchor_relation"] == "unknown"
    assert len(calls) == 1


@pytest.mark.parametrize("anchor_index,relation,states", [
    (None, "same_event", ["present"] * 8),
    (None, "different_event", ["present"] * 8),
    (None, "unknown", ["present"] * 8),
    (7, "not_applicable", ["absent"] * 8),
    (7, "not_applicable", ["absent"] * 6 + ["present", "present"]),
])
def test_extent_v4_rejects_relation_outside_request_role_schema(anchor_index, relation, states):
    images, samples = extent_frames()
    raw = extent_answer(states, query_support="partial", anchor_relation=relation)
    with endpoint([(200, envelope(raw))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).inspect_extent("action", images, samples, 0, 7 if anchor_index == 7 else 8, anchor_index)
    assert error.value.code == "invalid_vlm_response" and len(calls) == 1
    body = json.loads(error.value.details["response_body"])
    assert json.loads(body["choices"][0]["message"]["content"])["anchor_relation"] == relation


def test_describe_sends_ordered_images_and_schema(caplog):
    images, samples = frames()
    with endpoint([(200, envelope())]) as (url, history):
        client = Client(url, "private-test-key")
        with caplog.at_level("INFO", logger="video_search"):
            result = client.describe(images, samples, 10, 12)
    assert result["summary"] == DESCRIPTION["summary"]
    assert result["_trace"]["upstream_request_id"] == "upstream-test-id"
    assert len(result["_trace"]["frame_sha256"]) == 2
    assert result["_trace"]["frame_sha256"][0] != result["_trace"]["frame_sha256"][1]
    assert result["_trace"]["elapsed_seconds"] > 0
    trace = next(record.fields for record in caplog.records if record.message == "vlm_response")
    assert json.loads(trace["response_body"]) == DESCRIPTION
    assert "private-test-key" not in str(trace)
    request = history[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer private-test-key"
    body = request["body"]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["temperature"] == body["seed"] == 0
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    content = body["messages"][0]["content"]
    assert content[0]["text"].endswith("Describe visible actions, objects, and state changes. Keep the summary concise; list uncertainty explicitly. Return the required JSON object.")
    assert "10.500000000" in content[1]["text"]
    assert "11.500000000" in content[3]["text"]
    encoded = content[2]["image_url"]["url"].split(",", 1)[1]
    with Image.open(BytesIO(base64.b64decode(encoded))) as image:
        assert image.size == (512, 384)
        assert image.getpixel((0, 0))[0] > 240
    assert images[0].size == (1024, 768)


def test_hosted_gemma_uses_own_identity_decoder_and_gateway_trace():
    images, samples = frames()
    response = {**envelope(), "model": GEMMA_MODEL_ID}
    with endpoint([(200, response)], gateway_id="gateway-test-id") as (url, history):
        client = Client(url, "private-test-key", provider="gemma")
        result = client.describe(images, samples, 10, 12)
    request = history[0]
    assert request["body"]["model"] == GEMMA_MODEL_ID
    assert request["body"]["reasoning_effort"] == "none"
    assert "chat_template_kwargs" not in request["body"]
    assert request["headers"]["X-Obleth-Boons"] == "off"
    assert request["body"]["response_format"]["json_schema"]["strict"] is True
    assert client.timeout == 600
    assert client.spec == GEMMA_SPEC
    assert "enable_thinking" not in client.spec
    assert result["_trace"]["gateway_request_id"] == "gateway-test-id"
    assert result["_trace"]["model"] == GEMMA_MODEL_ID
    assert result["_trace"]["revision"] == "hosted-unpinned"


def test_gemma_description_prompt_explains_fields_and_short_targets(tmp_path):
    images, samples = frames()
    response = {**envelope(), "model": GEMMA_MODEL_ID}
    with endpoint([(200, response)]) as (url, history):
        result = Client(url, "test-key", provider="gemma").describe(images, samples, 10, 12)
    body = history[0]["body"]
    prompt = body["messages"][0]["content"][0]["text"]
    assert "one compact JSON object" in prompt
    assert "300 characters" in prompt and "100 characters" in prompt
    assert "4 actions" in prompt and "8 objects" in prompt and "2 uncertainties" in prompt
    for field in ("summary", "actions", "objects", "uncertainties"):
        assert f'"{field}"' in prompt
    assert "Example shape only" in prompt
    assert "Do not copy the example" in prompt
    assert body["max_tokens"] == 1024
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["summary"]["maxLength"] == 600
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"summary", "actions", "objects", "uncertainties"}
    settings = Settings("unused", tmp_path, vision_provider="gemma")
    spec = analysis.description_spec(settings)
    assert spec["prompt_version"] == "visible-evidence-gemma-json-v2"
    old_spec = {**spec, "prompt_version": "visible-evidence-v1"}
    assert store._description_key(spec) != store._description_key(old_spec)
    assert result["_trace"]["prompt_version"] == spec["prompt_version"]
    assert analysis.description_spec()["prompt_version"] == "visible-evidence-v1"


def test_gemma_truncated_whitespace_reply_still_fails_without_retry():
    images, samples = frames()
    content = '{"summary":"' + "x" * 600 + '"' + " \t" * 638
    response = {"model": GEMMA_MODEL_ID, "choices": [{"finish_reason": "length", "message": {"content": content}}]}
    with endpoint([(200, response)], gateway_id="private-test-key") as (url, history):
        with pytest.raises(VLMError) as error:
            Client(url, "private-test-key", provider="gemma").describe(images, samples, 10, 12)
    assert len(history) == 1
    assert error.value.code == "invalid_vlm_response"
    details = error.value.details
    assert details["status"] == 200
    assert details["params"]["task"] == "describe"
    assert details["gateway_request_id"] == "[redacted]"
    assert details["upstream_request_id"] == "upstream-test-id"
    assert details["request_id"]
    assert '"finish_reason": "length"' in details["response_body"]
    assert "private-test-key" not in json.dumps(details)


def test_gemma_verification_prompt_does_not_use_description_template():
    images, samples = frames()
    answer = {"status": "match", "intervals": [{"start_seconds": 10.5, "end_seconds": 11.5}],
              "observation": "The red object is visible."}
    response = {**envelope(answer), "model": GEMMA_MODEL_ID}
    with endpoint([(200, response)]) as (url, history):
        Client(url, "test-key", provider="gemma").verify("find the red object", images, samples, 10, 12)
    prompt = history[0]["body"]["messages"][0]["content"][0]["text"]
    assert "Check this user query:" in prompt
    assert "For matches give supported intervals inside the provided bounds" in prompt
    assert '"summary"' not in prompt and '"actions"' not in prompt
    assert history[0]["body"]["max_tokens"] == 2048


@pytest.mark.parametrize("model", [MODEL_ID, None])
def test_hosted_gemma_rejects_other_or_missing_response_identity(model):
    images, samples = frames()
    response = {**envelope(), "model": model}
    with endpoint([(200, response)], gateway_id="gateway-test-id") as (url, _):
        with pytest.raises(VLMError) as error:
            Client(url, "private-test-key", provider="gemma").describe(images, samples, 10, 12)
    assert error.value.code == "invalid_vlm_response"
    assert error.value.details["gateway_request_id"] == "gateway-test-id"


def test_hosted_gemma_errors_keep_gateway_trace_and_redact_key():
    images, samples = frames()
    with endpoint([(400, {"error": "private-test-key"})], gateway_id="private-test-key") as (url, history):
        with pytest.raises(VLMError) as error:
            Client(url, "private-test-key", provider="gemma").describe(images, samples, 10, 12)
    assert len(history) == 1
    assert error.value.details["status"] == 400
    assert error.value.details["gateway_request_id"] == "[redacted]"
    assert error.value.details["params"]["model"] == GEMMA_MODEL_ID
    assert "private-test-key" not in json.dumps(error.value.details)


def test_hosted_gemma_requires_key_and_correct_catalog_identity():
    with pytest.raises(VLMError) as error:
        Client("http://127.0.0.1:1/v1", provider="gemma")
    assert error.value.code == "vlm_not_configured"
    with pytest.raises(VLMError):
        Client("http://127.0.0.1:1/v1", "key", MODEL_ID, provider="gemma")


@pytest.mark.parametrize("status,provider", [(301, "gemma"), (302, "gemma"), (303, "gemma"),
                                             (307, "gemma"), (308, "gemma"), (302, "qwen")])
def test_model_redirects_never_send_credentials_to_destination(status, provider):
    calls = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_GET

        def log_message(self, *_):
            pass

    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)
    thread = Thread(target=destination.serve_forever, daemon=True)
    thread.start()
    images, samples = frames()
    try:
        target = f"http://127.0.0.1:{destination.server_port}/stolen"
        with endpoint([(status, {"error": "redirect private-test-key"})],
                      gateway_id="gateway-redirect-id", redirect_to=target) as (url, history):
            with pytest.raises(VLMError) as error:
                Client(url, "private-test-key", provider=provider).describe(images, samples, 10, 12)
        assert calls == []
        assert len(history) == 1
        assert error.value.code == "vlm_request_failed"
        assert error.value.details["status"] == status
        assert error.value.details["gateway_request_id"] == "gateway-redirect-id"
        assert error.value.details["upstream_request_id"] == "upstream-test-id"
        assert error.value.details["request_id"]
        assert "[redacted]" in error.value.details["response_body"]
        assert "private-test-key" not in json.dumps(error.value.details)
    finally:
        destination.shutdown()
        destination.server_close()
        thread.join(timeout=5)


def test_gemma_verification_has_short_json_contract_and_separate_prompt_version():
    images, samples = frames()
    answer = {"status": "no_match", "intervals": [], "observation": "The object is not visible."}
    response = {**envelope(answer), "model": GEMMA_MODEL_ID}
    before = analysis.description_spec(Settings("unused", ".", vision_provider="gemma"))
    with endpoint([(200, response)]) as (url, history):
        result = Client(url, "test-key", provider="gemma").verify("find object", images, samples, 10, 12)
    body = history[0]["body"]
    prompt = body["messages"][0]["content"][0]["text"]
    assert '"status"' in prompt and '"intervals"' in prompt and '"observation"' in prompt
    assert "300 characters" in prompt and "one line" in prompt
    assert result["_trace"]["prompt_version"] == "visible-evidence-gemma-verification-json-v2"
    assert before["prompt_version"] == "visible-evidence-gemma-json-v2"
    assert body["max_tokens"] == 2048
    assert Verification.model_json_schema()["$defs"]["MatchVerification"]["properties"]["observation"]["maxLength"] == 1200


def test_gemma_verification_rejects_truncated_whitespace_without_repair():
    images, samples = frames()
    text = '{"status":"no_match","intervals":[],"observation":"' + "x" * 1200 + '"' + " " * 2048
    response = {"model": GEMMA_MODEL_ID, "choices": [{"finish_reason": "length", "message": {"content": text}}]}
    with endpoint([(200, response)]) as (url, calls):
        with pytest.raises(VLMError) as caught:
            Client(url, "test-key", provider="gemma").verify("find object", images, samples, 10, 12)
    assert caught.value.code == "invalid_vlm_response"
    assert len(calls) == 1


def test_verify_validates_supported_intervals():
    images, samples = frames()
    answer = {"status": "match", "intervals": [{"start_seconds": 10.5, "end_seconds": 11.5}],
              "observation": "The red object is visible in the supplied frame."}
    with endpoint([(200, envelope(answer))]) as (url, history):
        result = Client(url).verify("find the red object", images, samples, 10, 12)
    assert result["status"] == "match"
    assert result["intervals"] == answer["intervals"]
    schema = history[0]["body"]["response_format"]["json_schema"]["schema"]
    assert schema["anyOf"]
    assert schema["$defs"]["MatchVerification"]["properties"]["intervals"]["minItems"] == 1
    assert schema["$defs"]["NonMatchVerification"]["properties"]["intervals"]["maxItems"] == 0
    assert len(result["_trace"]["schema_sha256"]) == 64


@pytest.mark.parametrize("provider", ["qwen", "gemma"])
@pytest.mark.parametrize("point", [0.0, 6.9])
def test_verification_point_evidence_is_retained_without_invented_duration(provider, point, caplog):
    images = [Image.new("RGB", (32, 32), "red")]
    samples = [{"source_seconds": point}]
    raw = {"status": "match", "intervals": [{"start_seconds": point, "end_seconds": point}],
           "observation": "One observed instant shows the action."}
    response = {**envelope(raw), "model": GEMMA_MODEL_ID if provider == "gemma" else MODEL_ID}
    with endpoint([(200, response)]) as (url, calls):
        with caplog.at_level("INFO", logger="video_search"):
            result = Client(url, "test-key", provider=provider).verify("action", images, samples, 0, 8)
    assert result["intervals"] == raw["intervals"] and len(calls) == 1
    assert result["_trace"]["verification_schema_version"] == "status-intervals-v3-points"
    prompt = calls[0]["body"]["messages"][0]["content"][0]["text"]
    assert "equal" in prompt and "one observed instant" in prompt and "Do not invent duration" in prompt
    assert calls[0]["body"]["max_tokens"] == 2048
    logged = next(record.fields for record in caplog.records if record.message == "vlm_response")
    assert json.loads(logged["response_body"]) == raw


@pytest.mark.parametrize("start,end,code", [
    (6.9, 6.8, "invalid_vlm_response"),
    (-0.1, -0.1, "invalid_vlm_response"),
    (8.1, 8.1, "invalid_vlm_interval"),
])
def test_verification_point_contract_still_rejects_reversed_negative_or_outside_evidence(start, end, code):
    images = [Image.new("RGB", (32, 32), "red")]
    samples = [{"source_seconds": 6.9}]
    raw = {"status": "match", "intervals": [{"start_seconds": start, "end_seconds": end}], "observation": "Claimed evidence."}
    with endpoint([(200, envelope(raw))]) as (url, calls):
        with pytest.raises(VLMError) as error:
            Client(url).verify("action", images, samples, 0, 8)
    assert error.value.code == code and len(calls) == 1
    assert error.value.details["status"] == 200 and error.value.details["request_id"]


@pytest.mark.parametrize("status", ["no_match", "insufficient_evidence"])
def test_verify_accepts_empty_intervals_for_nonmatch(status):
    images, samples = frames()
    answer = {"status": status, "intervals": [], "observation": "No direct evidence of the query."}
    with endpoint([(200, envelope(answer))]) as (url, _):
        result = Client(url).verify("find object", images, samples, 10, 12)
    assert result["status"] == status
    assert result["intervals"] == []


@pytest.mark.parametrize("answer", [
    {"status": "match", "intervals": [{"start_seconds": 9.0, "end_seconds": 11.5}], "observation": "Visible"},
    {"status": "match", "intervals": [{"start_seconds": 10.5, "end_seconds": 13.0}], "observation": "Visible"},
])
def test_outside_intervals_are_rejected(answer):
    images, samples = frames()
    with endpoint([(200, envelope(answer))]) as (url, _):
        with pytest.raises(VLMError) as error:
            Client(url).verify("find object", images, samples, 10, 12)
    assert error.value.code == "invalid_vlm_interval"


def test_transient_http_errors_retry_and_redact(caplog):
    images, samples = frames()
    with endpoint([(500, {"error": "private-test-key"}), (429, {"error": "busy"}), (200, envelope())]) as (url, history):
        result = Client(url, "private-test-key").describe(images, samples, 10, 12)
    assert result["summary"]
    assert len(history) == 3
    assert result["_trace"]["http_attempts"] == 3
    retries = [record for record in caplog.records if record.message == "vlm_retry"]
    assert len(retries) == 2
    assert "private-test-key" not in str([record.fields for record in retries])
    assert retries[0].fields["status"] == 500


def test_bad_request_does_not_retry_or_expose_key():
    images, samples = frames()
    with endpoint([(400, {"error": "private-test-key"})], upstream_id="private-test-key") as (url, history):
        with pytest.raises(VLMError) as error:
            Client(url, "private-test-key").describe(images, samples, 10, 12)
    assert len(history) == 1
    assert error.value.code == "vlm_request_failed"
    assert error.value.details["status"] == 400
    assert error.value.details["params"]["frame_count"] == 2
    assert error.value.details["request_id"]
    assert "private-test-key" not in str(error.value.details)


def test_provider_key_echo_is_removed_from_results_and_logs(caplog):
    images, samples = frames()
    response = envelope({**DESCRIPTION, "summary": "A private-test-key object is visible."})
    response["usage"]["extra"] = {"private-test-key": ["private-test-key"]}
    with endpoint([(200, response)], upstream_id="private-test-key") as (url, _):
        with caplog.at_level("INFO", logger="video_search"):
            result = Client(url, "private-test-key").describe(images, samples, 10, 12)
    assert "private-test-key" not in json.dumps(result)
    assert result["_trace"]["usage"]["prompt_tokens"] == 20
    logs = [record.fields for record in caplog.records if record.message == "vlm_response"]
    assert logs
    assert "private-test-key" not in json.dumps(logs)


@pytest.mark.parametrize("response", [b"not JSON", b"\xff", envelope(finish="length"), envelope({**DESCRIPTION, "extra": "ignored?"}),
                                             envelope({**DESCRIPTION, "summary": " "}), {"choices": []},
                                             {"choices": [{"message": "invalid", "finish_reason": "stop"}]}])
def test_invalid_or_truncated_outputs_fail(response):
    images, samples = frames()
    with endpoint([(200, response)]) as (url, history):
        with pytest.raises(VLMError) as error:
            Client(url).describe(images, samples, 10, 12)
    assert error.value.code == "invalid_vlm_response"
    assert len(history) == 1


def test_oversized_response_fails():
    images, samples = frames()
    with endpoint([(200, b"x" * (1024 * 1024 + 1))]) as (url, _):
        with pytest.raises(VLMError) as error:
            Client(url).describe(images, samples, 10, 12)
    assert error.value.code == "response_too_large"


@pytest.mark.parametrize("url", ["", "file:///tmp/file", "http://user:password@localhost/v1", "http://localhost/v1?secret=yes", "http://localhost/#frag"])
def test_invalid_endpoints_fail(url):
    with pytest.raises(VLMError):
        Client(url)


def test_frame_order_and_nonfinite_times_fail_before_network():
    images, samples = frames()
    client = Client("http://127.0.0.1:1/v1")
    for bad in ([{"source_seconds": 11.5}, {"source_seconds": 10.5}],
                [{"source_seconds": float("nan")}, {"source_seconds": 11.5}],
                [{"source_seconds": 9}, {"source_seconds": 11.5}]):
        with pytest.raises(VLMError) as error:
            client.describe(images, bad, 10, 12)
        assert error.value.code == "invalid_frames"


@pytest.mark.parametrize("data", [
    {"status": "no_match", "intervals": [{"start_seconds": 1.0, "end_seconds": 2.0}], "observation": "No"},
    {"status": "match", "intervals": [], "observation": "Match"},
    {"status": "match", "intervals": [{"start_seconds": float("nan"), "end_seconds": 2.0}], "observation": "Match"},
])
def test_verification_schema_rejects_conflicting_or_nonfinite_evidence(data):
    with pytest.raises(ValueError):
        Verification.model_validate(data)
