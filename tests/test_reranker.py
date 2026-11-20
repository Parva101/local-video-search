from copy import deepcopy
import math
import os
from pathlib import Path

import pytest

from video_search.encoder import EncoderError
from video_search.reranker import FILES, REVISION, SPEC, _candidate_texts, checkpoint_path, get_reranker


def candidate(summary, actions=None, objects=None):
    return {"recording_id": "recording-one", "start_seconds": 0, "end_seconds": 10,
            "description": {"summary": summary, "actions": actions or [], "objects": objects or [],
                            "uncertainties": [], "_trace": {"request_id": "source-call"}}}


def test_missing_reranker_requires_explicit_download(tmp_path):
    with pytest.raises(EncoderError, match="reranker download") as error:
        get_reranker(tmp_path)
    assert error.value.code == "model_not_installed"
    assert not checkpoint_path(tmp_path).exists()
    assert REVISION == "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    assert "model.safetensors" in FILES and not any(name.endswith(".bin") for name in FILES)


def test_candidate_texts_match_index_recipe_without_trace_or_uncertainty():
    item = candidate("A chef stands at a counter.", ["Slices a pizza"], ["knife"])
    item["description"]["uncertainties"] = ["The pizza topping is unclear."]
    original = deepcopy(item)
    assert _candidate_texts("pizza", [item]) == ["A chef stands at a counter. Slices a pizza knife"]
    assert item == original
    assert _candidate_texts("pizza", []) == []


@pytest.mark.parametrize("query,candidates", [
    (" ", [candidate("A chef.")]), ("x" * 1001, [candidate("A chef.")]),
    ("pizza", [{}]), ("pizza", [{"description": None}]),
    ("pizza", [{"description": {"summary": "A chef."}}]),
    ("pizza", [candidate("A chef.", actions="slices")]),
    ("pizza", [candidate("A chef.")] * 25),
])
def test_invalid_rerank_input_is_explicit(query, candidates):
    with pytest.raises(EncoderError):
        _candidate_texts(query, candidates)


@pytest.fixture
def real_reranker():
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 after downloading the pinned reranker")
    return get_reranker(Path(os.environ.get("MODEL_CACHE", "/models")))


def test_real_reranker_orders_scores_and_preserves_candidates(real_reranker):
    candidates = [candidate("A driver parks a blue car outside a house."),
                  candidate("A chef cuts a pizza into slices with a knife.", ["Cuts pizza"], ["pizza", "knife"]),
                  candidate("A dog plays with a ball in a garden.")]
    original = deepcopy(candidates)
    ranked = real_reranker.rank("Who cuts the pizza into slices?", candidates)
    assert ranked[0]["retrieval_rank"] == 2
    assert sorted(item["retrieval_rank"] for item in ranked) == [1, 2, 3]
    scores = [item["rerank_score"] for item in ranked]
    assert scores == sorted(scores, reverse=True) and all(math.isfinite(score) for score in scores)
    assert candidates == original
    assert all(item is not candidates[item["retrieval_rank"] - 1] for item in ranked)
    assert real_reranker.rank("pizza", []) == []
    assert SPEC["max_tokens"] == 512 and SPEC["max_candidates"] == 24


def test_real_reranker_rejects_long_pairs_without_truncating(real_reranker):
    with pytest.raises(EncoderError, match="512-token") as error:
        real_reranker.rank("x " * 490, [candidate("red " * 100)])
    assert error.value.code == "text_too_long"


def test_real_reranker_ties_keep_retrieval_order(real_reranker):
    items = [candidate("A person slices a pizza.") for _ in range(3)]
    ranked = real_reranker.rank("pizza", items)
    assert [item["retrieval_rank"] for item in ranked] == [1, 2, 3]
    assert len({item["rerank_score"] for item in ranked}) == 1
