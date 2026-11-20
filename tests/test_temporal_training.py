import copy
import json
from pathlib import Path
import random

import numpy as np
import pytest
import torch

from video_search.temporal_training import (Features, GroundingDataset, bind_protocol, collate,
    load_array, predictions, quality_foreground_loss, read_metadata, restore_rng, rng_state,
    save_checkpoint, score_predictions, split_rows, upstream_model, stage_epoch,
    publish_epoch_artifacts, recover_pending_epoch, model_config, UPSTREAM_SHA256, validate_model)


def rows():
    return [{"qid": n, "query": "open door", "vid": f"video{n}", "duration": 3., "relevant_windows": [[1., 2.]]}
            for n in range(12)]


def test_split_is_source_disjoint_and_seed_independent():
    data = rows()
    data.append({**data[0], "qid": 20})
    train, dev = split_rows(data)
    assert len(train) + len(dev) == len(data)
    assert not {x["vid"] for x in train} & {x["vid"] for x in dev}
    assert set(x["qid"] for x in dev) == set(x["qid"] for x in split_rows(list(reversed(data)))[1])
    assert len({x["vid"] for x in dev}) == 2


def test_metadata_rejects_duplicate_ids_and_invalid_targets(tmp_path):
    path = tmp_path / "train.jsonl"
    data = rows()
    path.write_text("\n".join(map(json.dumps, data)), encoding="utf-8")
    assert read_metadata(path) == data
    for bad in ({**data[0], "relevant_windows": [[2., 1.]]}, {**data[0], "vid": "../outside"},
                {**data[0], "duration": float("inf")}, {**data[0], "relevant_windows": [[1., 4.]]}):
        path.write_text("\n".join(map(json.dumps, [bad, *data[1:]])), encoding="utf-8")
        with pytest.raises(ValueError):
            read_metadata(path)
    path.write_text("\n".join(map(json.dumps, [data[0], data[0], data[1]])), encoding="utf-8")
    with pytest.raises(ValueError):
        read_metadata(path)


def test_raw_author_dimension_is_adjusted_for_tef_once(tmp_path):
    raw = {"span_loss_type": "l1", "clip_length": 1., "t_feat_dim": 512,
           "v_feat_dim": 2816, "ctx_mode": "video_tef", "eval_mode": "add"}
    path = tmp_path / "opt.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert model_config(path)["v_feat_dim"] == 2818
    assert model_config(path)["use_tef"] is True
    path.write_text(json.dumps({**raw, "v_feat_dim": 2818}), encoding="utf-8")
    with pytest.raises(ValueError):
        model_config(path)
    path.write_text(json.dumps({**raw, "ctx_mode": "video"}), encoding="utf-8")
    assert model_config(path)["v_feat_dim"] == 2816
    actual = Path(__file__).resolve().parents[1] / ".codex-backups/outperform-20261114/opt.json"
    if actual.exists():
        assert json.loads(actual.read_bytes())["v_feat_dim"] == 2816
        assert model_config(actual)["v_feat_dim"] == 2818


def feature_files(tmp_path, data):
    paths = [tmp_path / name for name in ("slowfast", "clip", "text")]
    for path in paths:
        path.mkdir()
    for row in data:
        np.savez(paths[0] / f"{row['vid']}.npz", features=np.ones((4, 2304), dtype=np.float32))
        np.savez(paths[1] / f"{row['vid']}.npz", features=np.ones((3, 512), dtype=np.float32))
        np.savez(paths[2] / f"{row['qid']}.npz", last_hidden_state=np.ones((2, 512), dtype=np.float32))
    return paths


def test_preflight_alignment_normalization_and_short_target(tmp_path):
    data = rows()[:2]
    data[0]["relevant_windows"] = [[1.01, 1.02]]
    features = Features(data, *feature_files(tmp_path, data))
    assert features.videos["video0"].shape == (3, 2818)
    assert torch.allclose(features.videos["video0"][:, -2:], torch.tensor([[0., 1/3], [1/3, 2/3], [2/3, 1.]]))
    batch = collate([GroundingDataset(data, features)[i] for i in range(2)])
    assert batch[1]["src_vid_mask"].tolist() == [[1., 1., 1.], [1., 1., 1.]]
    assert batch[2]["timestamp_window"][0].tolist() == [0., 1., 0.]
    assert batch[2]["span_labels_nn"][0, 1].tolist() == pytest.approx([1.01/3, 1.02/3])


@pytest.mark.parametrize("array", [np.ones((2, 4)), np.full((2, 512), np.nan), np.zeros((2, 512)), np.ones((0, 512))])
def test_feature_validation_fails_without_substitution(tmp_path, array):
    path = tmp_path / "invalid.npz"
    np.savez(path, last_hidden_state=array)
    with pytest.raises(ValueError):
        load_array(path, "last_hidden_state", 512)
    with pytest.raises(FileNotFoundError):
        load_array(tmp_path / "missing.npz", "last_hidden_state", 512)


def test_quality_loss_uses_detached_iou_not_binary_foreground():
    probability = torch.tensor([[[.8], [.8], [.8]]], requires_grad=True)
    spans = torch.tensor([[[0., 1.], [0., .5], [0., 1.]]], requires_grad=True)
    targets = {"timestamp": torch.zeros((1, 3, 2)), "span_labels_nn": torch.tensor([[[0., 1.]] * 3]),
               "timestamp_window": torch.tensor([[1., 1., 0.]]), "timestamp_mask": torch.tensor([[1., 1., 0.]])}
    loss = quality_foreground_loss({"pred_logits": probability, "pred_spans": spans}, targets)
    expected = (-(torch.log(torch.tensor(.8))) - .5 * torch.log(torch.tensor(.8)) - .5 * torch.log(torch.tensor(.2))) / 2
    assert loss.item() == pytest.approx(expected.item())
    loss.backward()
    assert spans.grad is None
    assert probability.grad[0, 0] < 0
    assert probability.grad[0, 1] > 0
    assert probability.grad[0, 2] == 0


def test_prediction_top1_point_is_zero_not_promoted():
    data = rows()[:1]
    target = {"timestamp": torch.tensor([[[.5, .5], [.5, .5]]]), "timestamp_mask": torch.ones((1, 2))}
    output = {"pred_spans": torch.tensor([[[0., 0.], [-1/6, 1/6]]]), "pred_logits": torch.tensor([[[.9], [.8]]])}
    predicted = predictions(output, target, data)
    assert predicted[0]["pred_relevant_windows"][0] == [1.5, 1.5, .9]
    assert score_predictions(data, predicted)["R1@0.5"] == 0
    with pytest.raises(ValueError):
        score_predictions(data, [])
    for window in ([0., 1., float("nan")], [-1., 1., .5], [0., 5., .5]):
        with pytest.raises(ValueError):
            score_predictions(data, [{"qid": data[0]["qid"], "vid": data[0]["vid"], "pred_relevant_windows": [window]}])


def test_float32_clamp_rounding_matches_prediction_guard():
    data = [{"qid": 7, "vid": "precise", "duration": 30.38035, "relevant_windows": [[0., 30.38035]]}]
    target = {"timestamp": torch.tensor([[[.5, .5]]]), "timestamp_mask": torch.ones((1, 1))}
    output = {"pred_spans": torch.tensor([[[-1., 1.]]]), "pred_logits": torch.tensor([[[.9]]])}
    predicted = predictions(output, target, data)
    assert predicted[0]["pred_relevant_windows"][0][1] == 30.3804
    assert score_predictions(data, predicted)["R1@0.7"] == 1
    predicted[0]["pred_relevant_windows"][0][1] = 30.3805
    with pytest.raises(ValueError, match="qid=7.*vid=precise.*30.3805"):
        score_predictions(data, predicted)


def test_validation_reuses_inference_and_scores_complete_grid(tmp_path):
    class FixedGrounder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.anchor = torch.nn.Parameter(torch.tensor(0.))

        def forward(self, src_vid, src_txt, src_vid_mask, src_txt_mask):
            shape = (*src_vid_mask.shape, 2)
            spans = torch.zeros(shape, device=src_vid.device) + self.anchor
            spans[..., 0], spans[..., 1] = -1., 1.
            return {"pred_spans": spans, "pred_logits": torch.ones_like(spans[..., :1]) * .9}

    data = rows()[:3]
    features = Features(data, *feature_files(tmp_path, data))
    loader = torch.utils.data.DataLoader(GroundingDataset(data, features), batch_size=2, collate_fn=collate)
    model = FixedGrounder().train()
    metrics, predicted = validate_model(model, loader, data)
    assert not model.training
    assert metrics["queries"] == len(predicted) == 3
    assert [p["qid"] for p in predicted] == [row["qid"] for row in data]
    assert metrics == score_predictions(data, predicted)
    with pytest.raises(ValueError, match="nonempty"):
        validate_model(model, [], [])
    with pytest.raises(ValueError, match="grid differs"):
        validate_model(model, [], data)


def test_protocol_rejects_changed_settings(tmp_path):
    protocol = {"seed": 2018, "variant": "baseline"}
    assert bind_protocol(tmp_path, protocol) == bind_protocol(tmp_path, protocol)
    with pytest.raises(ValueError):
        bind_protocol(tmp_path, {**protocol, "seed": 2019})


def test_checkpoint_restores_optimizer_scheduler_and_rng(tmp_path):
    random.seed(3)
    np.random.seed(3)
    torch.manual_seed(3)
    model = torch.nn.Linear(2, 1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.01)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1)
    def step():
        optimizer.zero_grad()
        sample = torch.randn(2) * (random.random() + np.random.rand())
        loss = model(sample).square().mean()
        loss.backward()
        optimizer.step()
        scheduler.step()
    step()
    path = tmp_path / "latest.pt"
    save_checkpoint(path, {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                           "scheduler": scheduler.state_dict(), "rng": rng_state()})
    step()
    expected = copy.deepcopy(model.state_dict())
    saved = torch.load(path, weights_only=True)
    model.load_state_dict(saved["model"])
    optimizer.load_state_dict(saved["optimizer"])
    scheduler.load_state_dict(saved["scheduler"])
    restore_rng(saved["rng"])
    step()
    assert all(torch.equal(expected[k], model.state_dict()[k]) for k in expected)


@pytest.mark.parametrize("interruption", ["staged", "best", "artifacts"])
def test_interrupted_epoch_commit_retains_winner_and_recovers_once(tmp_path, interruption):
    identity = "frozen-protocol"
    state = {"protocol_sha256": identity, "model": {"weight": torch.tensor([2.])},
             "next_epoch": 1, "best": (.5, .6)}
    report = {"epoch": 1, "development": {"R1@0.5": .5, "mIoU": .6}, "best": (.5, .6)}
    predicted = [{"qid": 1, "pred_relevant_windows": [[1., 2., .7]]}]
    stage_epoch(tmp_path, state, report, predicted, True)
    pending = torch.load(tmp_path / "pending.pt", weights_only=True)
    if interruption == "best":
        save_checkpoint(tmp_path / "best.pt", pending)
    elif interruption == "artifacts":
        publish_epoch_artifacts(tmp_path, pending)
    assert not (tmp_path / "latest.pt").exists()
    assert recover_pending_epoch(tmp_path, identity)
    assert not recover_pending_epoch(tmp_path, identity)
    assert not (tmp_path / "pending.pt").exists()
    latest = torch.load(tmp_path / "latest.pt", weights_only=True)
    best = torch.load(tmp_path / "best.pt", weights_only=True)
    assert latest["next_epoch"] == best["next_epoch"] == 1
    assert torch.equal(best["model"]["weight"], state["model"]["weight"])
    assert json.loads((tmp_path / "development-epoch-001.json").read_bytes())["predictions"] == predicted
    assert [json.loads(line) for line in (tmp_path / "history.jsonl").read_bytes().splitlines()] == [json.loads(json.dumps(report))]
    state2 = {**state, "next_epoch": 2, "model": {"weight": torch.tensor([3.])}}
    stage_epoch(tmp_path, state2, {"epoch": 2, "development": {"R1@0.5": .4, "mIoU": .5}}, [], False)
    assert recover_pending_epoch(tmp_path, identity)
    assert torch.load(tmp_path / "latest.pt", weights_only=True)["next_epoch"] == 2
    assert torch.load(tmp_path / "best.pt", weights_only=True)["next_epoch"] == 1
    assert len((tmp_path / "history.jsonl").read_bytes().splitlines()) == 2


def test_pending_commit_rejects_other_protocol_and_conflicting_history(tmp_path):
    state = {"protocol_sha256": "one", "next_epoch": 1, "model": {}}
    report = {"epoch": 1, "development": {}}
    stage_epoch(tmp_path, state, report, [], False)
    with pytest.raises(ValueError, match="different training protocol"):
        recover_pending_epoch(tmp_path, "two")
    (tmp_path / "history.jsonl").write_text(json.dumps({**report, "changed": True}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="history differs"):
        recover_pending_epoch(tmp_path, "one")
    assert not (tmp_path / "latest.pt").exists()


@pytest.fixture
def pinned_upstream(tmp_path):
    source = Path(__file__).resolve().parents[1] / ".codex-backups/outperform-20261114/UniVTG"
    if not source.exists():
        pytest.skip("Pinned author research checkout is not installed")
    upstream = tmp_path / "upstream"
    for relative, expected in UPSTREAM_SHA256.items():
        if expected is not None:
            path = upstream / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            # Git's Windows checkout conversion is removed only in this test fixture.
            path.write_bytes((source / relative).read_bytes().replace(b"\r\n", b"\n"))
    return upstream


def test_tampered_upstream_fails_before_import(pinned_upstream):
    path = pinned_upstream / "model/univtg.py"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="runtime source differs"):
        upstream_model(pinned_upstream, {})


def test_upstream_model_real_forward_and_criterion(pinned_upstream):
    upstream = pinned_upstream
    config = dict(device="cpu", hidden_dim=16, dropout=0., droppath=0., nheads=2, dim_feedforward=16,
                  enc_layers=1, dec_layers=1, pre_norm=False, position_embedding="sine", max_q_l=75,
                  t_feat_dim=512, v_feat_dim=2818, input_dropout=0., span_loss_type="l1", use_txt_pos=False,
                  n_input_proj=1, set_cost_span=10, set_cost_giou=1, set_cost_class=1, max_v_l=75,
                  b_loss_coef=10, g_loss_coef=1, f_loss_coef=10, s_loss_intra_coef=1, s_loss_inter_coef=.5,
                  dset_type="mr", train_path="train.jsonl", eos_coef=.1, temperature=.07, saliency_margin=1)
    model, criterion = upstream_model(upstream, config)
    inputs = {"src_vid": torch.randn(2, 4, 2818), "src_txt": torch.randn(2, 3, 512),
              "src_vid_mask": torch.ones(2, 4), "src_txt_mask": torch.ones(2, 3)}
    target = {"timestamp": torch.tensor([[[.125, .125], [.375, .375], [.625, .625], [.875, .875]]] * 2),
              "timestamp_mask": torch.ones(2, 4), "timestamp_window": torch.tensor([[0., 1., 1., 0.]] * 2),
              "span_labels_nn": torch.tensor([[[0., 0.], [.25, .75], [.25, .75], [0., 0.]]] * 2),
              "saliency_scores": torch.tensor([[0., 1., 1., 0.]] * 2), "saliency_pos_labels": torch.tensor([[1], [1]])}
    result = model(**inputs)
    losses = criterion(result, target)
    total = sum(v * criterion.weight_dict[k] for k, v in losses.items())
    assert torch.isfinite(total)
    total.backward()
    assert any(p.grad is not None for p in model.parameters())
