"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    tp = sum(1 for h, j in zip(human, judge) if h == POS and j == POS)
    fp = sum(1 for h, j in zip(human, judge) if h != POS and j == POS)
    fn = sum(1 for h, j in zip(human, judge) if h == POS and j != POS)
    tn = sum(1 for h, j in zip(human, judge) if h != POS and j != POS)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p = cm["tp"] / (cm["tp"] + cm["fp"]) if (cm["tp"] + cm["fp"]) > 0 else 0.0
    r = cm["tp"] / (cm["tp"] + cm["fn"]) if (cm["tp"] + cm["fn"]) > 0 else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    if len(human) != len(judge) or len(human) == 0:
        raise ValueError("empty or unequal length sequence")
    n = len(human)
    p_o = sum(1 for h, j in zip(human, judge) if h == j) / n
    categories = set(human) | set(judge)
    p_e = sum((human.count(c) / n) * (judge.count(c) / n) for c in categories)
    if abs(1.0 - p_e) < 1e-12:
        raise ValueError("Cohen's kappa is undefined when p_e == 1 (constant judge)")
    return float((p_o - p_e) / (1.0 - p_e))


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if denom == 0.0:
        return 0.0
    val = (observed_rate + specificity - 1.0) / denom
    return float(max(0.0, min(1.0, val)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    list_a, list_b = list(a), list(b)
    if len(list_a) != len(list_b):
        raise ValueError("Sequences a and b must have the same length")
    if list_a == list_b:
        return 0.0, 0.0, 0.0

    diff = float(np.mean(list_a) - np.mean(list_b))

    def stat(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    random_gen = np.random.default_rng(rng)
    res = stats.bootstrap(
        (list_a, list_b),
        stat,
        paired=True,
        method="percentile",
        n_resamples=n_resamples,
        random_state=random_gen,
        confidence_level=confidence,
    )
    lo = float(res.confidence_interval.low)
    hi = float(res.confidence_interval.high)
    return diff, lo, hi


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if k <= 0 or k > n or c < 0 or c > n or n <= 0:
        raise ValueError(f"Invalid arguments for pass_at_k: n={n}, c={c}, k={k}")
    if n - c < k:
        return 1.0
    return float(1.0 - math.comb(n - c, k) / math.comb(n, k))


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if k <= 0 or k > n or c < 0 or c > n or n <= 0:
        raise ValueError(f"Invalid arguments for pass_hat_k: n={n}, c={c}, k={k}")
    if c < k:
        return 0.0
    return float(math.comb(c, k) / math.comb(n, k))
