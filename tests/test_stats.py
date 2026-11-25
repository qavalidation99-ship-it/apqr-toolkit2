import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from apqr import Spec, capability, control_limits, descriptive, interpret_cpk, out_of_spec, trend_rules
from apqr.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_descriptive_basic():
    d = descriptive([1, 2, 3, 4, 5])
    assert d["n"] == 5
    assert d["mean"] == 3
    assert math.isclose(d["sd"], 1.5811388, rel_tol=1e-6)
    assert d["min"] == 1 and d["max"] == 5


def test_descriptive_ignores_nan():
    assert descriptive([1, float("nan"), 3])["n"] == 2


def test_control_limits_imr():
    # moving ranges: 2, 2, 2 -> MR-bar 2 -> sigma = 2/1.128
    lim = control_limits([10, 12, 10, 12])
    assert math.isclose(lim.mr_bar, 2)
    assert math.isclose(lim.sigma_within, 2 / 1.128)
    assert math.isclose(lim.ucl, 11 + 3 * 2 / 1.128)


def test_capability_two_sided():
    vals = [99, 101, 99, 101, 100, 100]
    cap = capability(vals, Spec(lsl=95, usl=105))
    sd = pd.Series(vals).std()
    assert math.isclose(cap.ppk, 5 / (3 * sd), rel_tol=1e-9)
    assert math.isclose(cap.pp, 10 / (6 * sd), rel_tol=1e-9)


def test_capability_one_sided():
    cap = capability([2.0, 2.2, 2.1, 2.3], Spec(usl=3.5))
    assert cap.pp is None and cap.ppk is not None


def test_out_of_spec():
    assert out_of_spec([90, 100, 110, float("nan")], Spec(lsl=95, usl=105)) == [0, 2]


def test_rule_drift_detected():
    rules = {v.rule for v in trend_rules([1, 2, 3, 4, 5, 6, 7, 6, 5])}
    assert "Rule 3" in rules


def test_rule_shift_detected():
    vals = [10, 9, 10, 9, 10] + [12, 12.2, 11.9, 12.1, 12, 12.1, 11.9, 12.2, 12]
    assert "Rule 2" in {v.rule for v in trend_rules(vals)}


def test_interpret_cpk():
    assert interpret_cpk(2.0) == "Highly capable"
    assert interpret_cpk(0.8).startswith("Not capable")
    assert interpret_cpk(None) == "Not calculable"


def test_cli_end_to_end(tmp_path):
    out = tmp_path / "report"
    rc = main(["analyze", str(ROOT / "examples/sample_batches.csv"),
               "--spec", str(ROOT / "examples/specs.json"), "--out", str(out), "--product", "Demo"])
    assert rc == 0
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "dissolution_30min" in md and "B26028" in md  # seeded OOS batch
    assert (out / "report.html").exists()
    assert list((out / "charts").glob("*.png"))


def test_missing_batch_column(tmp_path):
    csv = tmp_path / "d.csv"
    csv.write_text("lot,assay\n1,100\n2,101\n")
    with pytest.raises(KeyError):
        main(["analyze", str(csv), "--spec", str(ROOT / "examples/specs.json"), "--out", str(tmp_path / "o")])
