"""Offline interval estimates from caption scores, not observed frame evidence."""

import math


VERSION = "overlap-weighted-caption-curve-v1"
MAX_CELLS = 86400
MAX_KERNEL_RADIUS = 256


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _project(windows, duration, step, score_field):
    count = math.ceil(duration / step)
    values, weights = [0.] * (count + 1), [0.] * (count + 1)
    parsed, seen = [], set()
    for window in windows:
        if not isinstance(window, dict) or any(k not in window for k in ("start_seconds", "end_seconds", score_field)):
            raise ValueError("Each window needs source bounds and its score")
        start, end, score = (_number(window[k], k) for k in ("start_seconds", "end_seconds", score_field))
        if not 0 <= start < end <= duration:
            raise ValueError("Window must be positive and inside the source")
        if (start, end) in seen:
            raise ValueError("Duplicate window bounds")
        seen.add((start, end))
        parsed.append((start, end, score))
    covered = 0.
    for start, end, score in sorted(parsed):
        if start > covered:
            raise ValueError("Caption windows leave an uncovered source gap")
        covered = max(covered, end)
        first, last = int(start / step), min(count - 1, math.ceil(end / step) - 1)
        spans = [(first, first + 1, end - start)] if first == last else [
            (first, first + 1, (first + 1) * step - start),
            (first + 1, last, step), (last, last + 1, end - last * step)]
        for left, right, overlap in spans:
            if left < right:
                values[left] += score * overlap
                values[right] -= score * overlap
                weights[left] += overlap
                weights[right] -= overlap
    if covered != duration:
        raise ValueError("Caption windows do not cover the full source")
    value_sum, weight_sum, curve = 0., 0., []
    for value, weight in zip(values[:-1], weights[:-1]):
        value_sum += value
        weight_sum += weight
        if weight_sum <= 0 or not math.isfinite(value_sum) or not math.isfinite(weight_sum):
            raise ValueError("Projected caption evidence has invalid weight or magnitude")
        curve.append(value_sum / weight_sum)
    widths = [min(step, duration - i * step) for i in range(count)]
    return curve, widths


def decode(windows, duration, *, score_field="rerank_score", sigma_seconds=0,
           background_weight=0, step_seconds=1):
    """Return zero or one estimated span; a relative score is no absence probability.

    Overlapping captions contribute in proportion to their overlap with each cell.
    Gaussian smoothing uses a three-sigma kernel and renormalizes at source edges.
    Background contrast subtracts the neighboring-cell mean before centering.
    """
    duration = _number(duration, "duration")
    step = _number(step_seconds, "step_seconds")
    sigma = _number(sigma_seconds, "sigma_seconds")
    background = _number(background_weight, "background_weight")
    if duration <= 0 or step <= 0 or duration / step > MAX_CELLS:
        raise ValueError("Use a positive duration and step with at most 86400 cells")
    if sigma < 0 or not 0 <= background <= 1:
        raise ValueError("Sigma must be nonnegative and background_weight within [0, 1]")
    if not isinstance(score_field, str) or not score_field:
        raise ValueError("score_field must name a score")
    if not isinstance(windows, (list, tuple)) or not windows:
        raise ValueError("A full set of caption windows is required")
    radius = math.ceil(3 * sigma / step) if sigma else 0
    if radius > MAX_KERNEL_RADIUS:
        raise ValueError("Gaussian radius exceeds 256 cells; increase step_seconds")
    curve, widths = _project(windows, duration, step, score_field)
    count = len(curve)
    if sigma:
        centers = [i * step + width / 2 for i, width in enumerate(widths)]
        smoothed = []
        for i, center in enumerate(centers):
            neighbors = range(max(0, i - radius), min(count, i + radius + 1))
            kernel = [(j, math.exp(-.5 * ((centers[j] - center) / sigma) ** 2) * widths[j])
                      for j in neighbors]
            smoothed.append(math.fsum(curve[j] * weight for j, weight in kernel)
                            / math.fsum(weight for _, weight in kernel))
        curve = smoothed
    if background and count > 1:
        value_prefix, time_prefix = [0.], [0.]
        for value, width in zip(curve, widths):
            value_prefix.append(value_prefix[-1] + value * width)
            time_prefix.append(time_prefix[-1] + width)
        contrasted = []
        for i, value in enumerate(curve):
            left, right = max(0, i - max(1, radius)), min(count, i + max(1, radius) + 1)
            outer_sum = value_prefix[right] - value_prefix[left] - value * widths[i]
            outer_width = time_prefix[right] - time_prefix[left] - widths[i]
            contrasted.append(value - background * outer_sum / outer_width)
        curve = contrasted
    if not all(math.isfinite(value) for value in curve):
        raise ValueError("Temporal curve has an invalid magnitude")
    if math.isclose(max(curve), min(curve), rel_tol=1e-12, abs_tol=1e-15):
        return []
    mean = math.fsum(value * width for value, width in zip(curve, widths)) / duration
    best, current, left, best_left, best_right = 0., 0., 0, 0, 0
    for i, (value, width) in enumerate(zip(curve, widths)):
        if current <= 0:
            current, left = 0., i
        current += (value - mean) * width
        if current > best:
            best, best_left, best_right = current, left, i + 1
    if best <= 0:
        return []
    return [{"start_seconds": best_left * step, "end_seconds": min(duration, best_right * step),
             "score": best, "method": VERSION, "boundary_kind": "estimated",
             "score_semantics": "mean-centered-relative-caption-evidence-seconds",
             "checked_by_model": False, "verified": False}]
