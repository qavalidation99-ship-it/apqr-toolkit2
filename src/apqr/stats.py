"""Statistical calculations used in an Annual Product Quality Review (APQR / PQR).

All functions work on a 1-D sequence of results in batch (manufacturing) order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

# d2 constant for moving ranges of span 2 (individuals chart)
D2 = 1.128
# D4 constant for the moving-range chart (n = 2)
D4 = 3.267


@dataclass
class Spec:
    """Specification limits for one parameter. Either limit may be None (one-sided spec)."""

    lsl: Optional[float] = None
    usl: Optional[float] = None
    unit: str = ""
    target: Optional[float] = None


@dataclass
class ControlLimits:
    center: float
    ucl: float
    lcl: float
    sigma_within: float
    mr_bar: float
    mr_ucl: float


@dataclass
class Capability:
    cp: Optional[float]
    cpk: Optional[float]
    pp: Optional[float]
    ppk: Optional[float]


@dataclass
class RuleViolation:
    rule: str
    description: str
    indices: list[int] = field(default_factory=list)


def _clean(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    return arr[~np.isnan(arr)]


def descriptive(values: Sequence[float]) -> dict:
    x = _clean(values)
    if x.size == 0:
        raise ValueError("No numeric results to analyse.")
    sd = float(np.std(x, ddof=1)) if x.size > 1 else 0.0
    mean = float(np.mean(x))
    return {
        "n": int(x.size),
        "mean": mean,
        "sd": sd,
        "rsd_pct": (sd / mean * 100) if mean else float("nan"),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "median": float(np.median(x)),
    }


def control_limits(values: Sequence[float]) -> ControlLimits:
    """Individuals / moving-range (I-MR) control limits.

    Within-batch sigma is estimated from the average moving range (MR-bar / d2),
    which is the standard approach for one result per batch.
    """
    x = _clean(values)
    if x.size < 2:
        raise ValueError("At least 2 results are needed for control limits.")
    mr = np.abs(np.diff(x))
    mr_bar = float(np.mean(mr))
    sigma_w = mr_bar / D2
    center = float(np.mean(x))
    return ControlLimits(
        center=center,
        ucl=center + 3 * sigma_w,
        lcl=center - 3 * sigma_w,
        sigma_within=sigma_w,
        mr_bar=mr_bar,
        mr_ucl=D4 * mr_bar,
    )


def _index(spread: float, mean: float, spec: Spec, sigma: float) -> tuple[Optional[float], Optional[float]]:
    """Return (potential index, actual index) for a given sigma estimate."""
    if sigma <= 0:
        return None, None
    potential = None
    if spec.lsl is not None and spec.usl is not None:
        potential = (spec.usl - spec.lsl) / (6 * sigma)
    sides = []
    if spec.usl is not None:
        sides.append((spec.usl - mean) / (3 * sigma))
    if spec.lsl is not None:
        sides.append((mean - spec.lsl) / (3 * sigma))
    actual = min(sides) if sides else None
    return potential, actual


def capability(values: Sequence[float], spec: Spec) -> Capability:
    """Cp/Cpk use within-batch sigma (MR-bar/d2); Pp/Ppk use overall sample SD."""
    x = _clean(values)
    mean = float(np.mean(x))
    sigma_overall = float(np.std(x, ddof=1)) if x.size > 1 else 0.0
    sigma_within = control_limits(x).sigma_within if x.size > 1 else 0.0
    cp, cpk = _index(0, mean, spec, sigma_within)
    pp, ppk = _index(0, mean, spec, sigma_overall)
    return Capability(cp=cp, cpk=cpk, pp=pp, ppk=ppk)


def out_of_spec(values: Sequence[float], spec: Spec) -> list[int]:
    """Indices (in the original sequence) of results outside the specification."""
    arr = np.asarray(values, dtype=float)
    idx = []
    for i, v in enumerate(arr):
        if np.isnan(v):
            continue
        if (spec.lsl is not None and v < spec.lsl) or (spec.usl is not None and v > spec.usl):
            idx.append(i)
    return idx


def trend_rules(values: Sequence[float], limits: Optional[ControlLimits] = None) -> list[RuleViolation]:
    """Apply common Nelson / Western Electric rules for out-of-trend (OOT) signals.

    Rule 1: one point beyond 3 sigma.
    Rule 2: nine points in a row on the same side of the centre line.
    Rule 3: six points in a row steadily increasing or decreasing.
    Rule 5: two out of three points beyond 2 sigma on the same side.
    Indices refer to positions in the cleaned (non-missing) sequence.
    """
    x = _clean(values)
    lim = limits or control_limits(x)
    c, s = lim.center, lim.sigma_within
    out: list[RuleViolation] = []

    r1 = [i for i, v in enumerate(x) if s > 0 and abs(v - c) > 3 * s]
    if r1:
        out.append(RuleViolation("Rule 1", "Point beyond 3σ control limit", r1))

    r2: set[int] = set()
    side = np.sign(x - c)
    for i in range(len(x) - 8):
        window = side[i : i + 9]
        if window[0] != 0 and np.all(window == window[0]):
            r2.update(range(i, i + 9))
    if r2:
        out.append(RuleViolation("Rule 2", "9 consecutive points on the same side of the mean (shift)", sorted(r2)))

    r3: set[int] = set()
    d = np.sign(np.diff(x))
    for i in range(len(d) - 4):
        window = d[i : i + 5]
        if window[0] != 0 and np.all(window == window[0]):
            r3.update(range(i, i + 6))
    if r3:
        out.append(RuleViolation("Rule 3", "6 consecutive points steadily increasing or decreasing (drift)", sorted(r3)))

    r5: set[int] = set()
    if s > 0:
        for i in range(len(x) - 2):
            window = x[i : i + 3]
            for sign in (1, -1):
                hits = [i + j for j, v in enumerate(window) if sign * (v - c) > 2 * s]
                if len(hits) >= 2:
                    r5.update(hits)
    if r5:
        out.append(RuleViolation("Rule 5", "2 of 3 consecutive points beyond 2σ on the same side", sorted(r5)))

    return out


def interpret_cpk(cpk: Optional[float]) -> str:
    """Common industry interpretation of Cpk / Ppk."""
    if cpk is None:
        return "Not calculable"
    if cpk >= 1.67:
        return "Highly capable"
    if cpk >= 1.33:
        return "Capable"
    if cpk >= 1.0:
        return "Marginally capable - monitor"
    return "Not capable - investigate"
