"""Turn batch data into an APQR statistical summary (Markdown + HTML + charts)."""
from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from . import stats
from .stats import Spec


@dataclass
class ParameterResult:
    name: str
    spec: Spec
    descriptive: dict
    limits: Optional[stats.ControlLimits]
    capability: Optional[stats.Capability]
    oos_batches: list[str]
    trend_violations: list[dict]
    chart: Optional[str] = None

    @property
    def verdict(self) -> str:
        if self.oos_batches:
            return "OOS results - CAPA required"
        if self.trend_violations:
            return "Out-of-trend signals - evaluate"
        if self.capability and self.capability.ppk is not None and self.capability.ppk < 1.0:
            return "In spec but not capable - evaluate"
        return "In control"


def load_specs(path: str | Path) -> dict[str, Spec]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: Spec(**values) for name, values in raw.items()}


def analyse(
    df: pd.DataFrame,
    specs: dict[str, Spec],
    batch_col: str = "batch",
    charts_dir: Optional[Path] = None,
) -> list[ParameterResult]:
    if batch_col not in df.columns:
        raise KeyError(f"Batch column '{batch_col}' not found. Columns: {list(df.columns)}")

    params = [c for c in df.columns if c in specs]
    if not params:
        raise ValueError("None of the CSV columns match a parameter in the spec file.")

    results = []
    for name in params:
        series = pd.to_numeric(df[name], errors="coerce")
        valid = series.notna()
        values = series[valid].to_numpy()
        batches = df.loc[valid, batch_col].astype(str).tolist()
        spec = specs[name]

        desc = stats.descriptive(values)
        limits = stats.control_limits(values) if len(values) >= 2 else None
        cap = stats.capability(values, spec) if len(values) >= 2 else None
        oos = [batches[i] for i in stats.out_of_spec(values, spec)]
        trends = []
        if limits:
            for v in stats.trend_rules(values, limits):
                trends.append({"rule": v.rule, "description": v.description,
                               "batches": [batches[i] for i in v.indices]})

        res = ParameterResult(name, spec, desc, limits, cap, oos, trends)
        if charts_dir is not None and limits:
            from .charts import control_chart

            res.chart = control_chart(name, batches, values, spec, limits, charts_dir)
        results.append(res)
    return results


def _f(v: Optional[float], nd: int = 3) -> str:
    if v is None:
        return "-"
    try:
        if v != v:  # NaN
            return "-"
    except TypeError:
        return str(v)
    return f"{v:.{nd}f}"


def _spec_text(s: Spec) -> str:
    if s.lsl is not None and s.usl is not None:
        return f"{s.lsl:g} – {s.usl:g} {s.unit}".strip()
    if s.lsl is not None:
        return f"≥ {s.lsl:g} {s.unit}".strip()
    if s.usl is not None:
        return f"≤ {s.usl:g} {s.unit}".strip()
    return "Report"


def to_markdown(results: list[ParameterResult], product: str = "", period: str = "") -> str:
    lines = [f"# APQR Statistical Summary{(' – ' + product) if product else ''}", ""]
    if period:
        lines.append(f"**Review period:** {period}  ")
    lines.append(f"**Generated:** {date.today().isoformat()} with apqr-toolkit  ")
    lines.append("")
    lines.append("| Parameter | Spec | n | Mean | SD | RSD % | Min | Max | Cpk | Ppk | OOS | Verdict |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        d, c = r.descriptive, r.capability
        lines.append(
            f"| {r.name} | {_spec_text(r.spec)} | {d['n']} | {_f(d['mean'])} | {_f(d['sd'])} | "
            f"{_f(d['rsd_pct'], 2)} | {_f(d['min'])} | {_f(d['max'])} | "
            f"{_f(c.cpk if c else None, 2)} | {_f(c.ppk if c else None, 2)} | {len(r.oos_batches)} | {r.verdict} |"
        )
    lines.append("")
    for r in results:
        lines.append(f"## {r.name}")
        lines.append("")
        if r.limits:
            lines.append(f"- Control limits (I-chart): LCL {_f(r.limits.lcl)} / CL {_f(r.limits.center)} / UCL {_f(r.limits.ucl)}")
        if r.capability:
            lines.append(f"- Capability: Ppk {_f(r.capability.ppk, 2)} → {stats.interpret_cpk(r.capability.ppk)}")
        lines.append(f"- OOS batches: {', '.join(r.oos_batches) if r.oos_batches else 'None'}")
        if r.trend_violations:
            for t in r.trend_violations:
                lines.append(f"- {t['rule']}: {t['description']} – batches {', '.join(t['batches'])}")
        else:
            lines.append("- Trend rules: no signals")
        if r.chart:
            lines.append(f"\n![{r.name} control chart]({r.chart})")
        lines.append("")
    lines.append("---")
    lines.append("*Statistics support, but do not replace, QA review and conclusions in the APQR.*")
    return "\n".join(lines) + "\n"


def to_html(markdown_text: str, title: str = "APQR Statistical Summary") -> str:
    """Minimal Markdown → HTML conversion (tables, headings, lists, images) with no extra deps."""
    import re

    out, in_table, in_list = [], False, False
    for line in markdown_text.splitlines():
        if line.startswith("|"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if all(set(c) <= {"-"} for c in cells):
                continue
            if not in_table:
                out.append("<table><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        m = re.match(r"!\[(.*)\]\((.*)\)", line.strip())
        if m:
            out.append(f'<img alt="{html.escape(m[1])}" src="{html.escape(m[2])}">')
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            txt = html.escape(line.strip())
            txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
            txt = re.sub(r"\*(.+?)\*", r"<i>\1</i>", txt)
            out.append(f"<p>{txt}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    css = ("body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}"
           "table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{border:1px solid #ccc;padding:6px;text-align:left}"
           "th{background:#f3f4f6}img{max-width:100%;border:1px solid #eee;margin:.5rem 0}")
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{css}</style></head><body>{''.join(out)}</body></html>")


def results_json(results: list[ParameterResult]) -> str:
    def conv(r: ParameterResult) -> dict:
        d = asdict(r)
        d["verdict"] = r.verdict
        return d

    return json.dumps([conv(r) for r in results], indent=2, ensure_ascii=False, default=str)
