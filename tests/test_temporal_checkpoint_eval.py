import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest
import torch


spec = importlib.util.spec_from_file_location("evaluate_temporal", Path(__file__).parents[1] / "scripts/evaluate_temporal_head.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("size", [0, -1, 129, True])
def test_batch_size_is_validated_before_allocating_hardware(size):
    with pytest.raises(ValueError, match="batch size"):
        module.evaluate(Namespace(batch_size=size))


def test_own_checkpoint_reads_only_safe_tensor_state(tmp_path):
    checkpoint = tmp_path / "model.pt"
    torch.save({"model": {"weight": torch.tensor([1.])}}, checkpoint)
    assert torch.equal(module.load_weights(checkpoint)["model"]["weight"], torch.tensor([1.]))
    torch.save({"wrong": 1}, checkpoint)
    with pytest.raises(ValueError, match="no model state"):
        module.load_weights(checkpoint)


def test_author_checkpoint_hash_must_match_before_load(tmp_path):
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"not a verified checkpoint")
    with pytest.raises(ValueError, match="verified download"):
        module.load_weights(checkpoint, author=True)


def test_evaluation_rejects_changed_training_source_and_evaluator(tmp_path):
    from video_search.temporal_training import digest
    config = tmp_path / "config.json"
    config.write_bytes(b"{}")
    protocol = {"raw_author_config_sha256": module.file_hash(config),
                "evaluator_sha256": module.file_hash(module.evaluator.__file__),
                "source_sha256": module.file_hash(Path(__file__).parents[1] / "src/video_search/temporal_training.py")}
    module.validate_training_protocol(protocol, {"protocol_sha256": digest(protocol)}, config)
    for key in protocol:
        changed = {**protocol, key: "0" * 64}
        with pytest.raises(ValueError, match="frozen run"):
            module.validate_training_protocol(changed, {"protocol_sha256": digest(changed)}, config)
