"""Control-chart plotting for APQR trend review."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .stats import ControlLimits, Spec, out_of_spec  # noqa: E402


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "parameter"


def control_chart(
    name: str,
    batches: Sequence[str],
    values: Sequence[float],
    spec: Spec,
    limits: ControlLimits,
    out_dir: Path,
) -> str:
    """Save an individuals (I) chart with control and specification limits. Returns the file name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = list(range(len(values)))
    ax.plot(x, values, marker="o", color="#1f4e79", linewidth=1.2, markersize=4, label="Result")

    oos = set(out_of_spec(values, spec))
    if oos:
        ax.scatter([i for i in oos], [values[i] for i in oos], color="#c00000", zorder=5, s=50, label="OOS")

    ax.axhline(limits.center, color="#2e7d32", linewidth=1, label=f"Mean {limits.center:.3g}")
    ax.axhline(limits.ucl, color="#ef6c00", linestyle="--", linewidth=1, label=f"UCL {limits.ucl:.3g}")
    ax.axhline(limits.lcl, color="#ef6c00", linestyle="--", linewidth=1, label=f"LCL {limits.lcl:.3g}")
    if spec.usl is not None:
        ax.axhline(spec.usl, color="#c00000", linewidth=1.3, label=f"USL {spec.usl:g}")
    if spec.lsl is not None:
        ax.axhline(spec.lsl, color="#c00000", linewidth=1.3, label=f"LSL {spec.lsl:g}")

    step = max(1, len(batches) // 25)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(list(batches)[::step], rotation=60, ha="right", fontsize=7)
    ax.set_title(f"{name} – I chart", fontsize=11)
    ax.set_ylabel(f"{name} {('(' + spec.unit + ')') if spec.unit else ''}".strip())
    ax.legend(fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5))
    ax.grid(alpha=0.25)
    fig.tight_layout()

    fname = f"{_slug(name)}_ichart.png"
    fig.savefig(out_dir / fname, dpi=130)
    plt.close(fig)
    return f"{out_dir.name}/{fname}"
