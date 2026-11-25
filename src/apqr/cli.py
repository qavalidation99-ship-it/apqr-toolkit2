"""Command-line interface: `apqr analyze data.csv --spec specs.json --out report/`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import __version__
from .report import analyse, load_specs, results_json, to_html, to_markdown


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="apqr", description="Statistical toolkit for Annual Product Quality Reviews (APQR/PQR).")
    p.add_argument("--version", action="version", version=f"apqr-toolkit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Analyse batch results and write an APQR statistical report.")
    a.add_argument("data", help="CSV file: one row per batch, one column per parameter.")
    a.add_argument("--spec", required=True, help="JSON file with specification limits per parameter.")
    a.add_argument("--out", default="apqr_report", help="Output folder (default: apqr_report).")
    a.add_argument("--batch-col", default="batch", help="Name of the batch-number column (default: batch).")
    a.add_argument("--product", default="", help="Product name for the report title.")
    a.add_argument("--period", default="", help="Review period, e.g. 'Jan–Dec 2026'.")
    a.add_argument("--no-charts", action="store_true", help="Skip control-chart images.")

    args = p.parse_args(argv)

    if args.command == "analyze":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        df = pd.read_csv(args.data)
        specs = load_specs(args.spec)
        results = analyse(df, specs, batch_col=args.batch_col,
                          charts_dir=None if args.no_charts else out / "charts")
        md = to_markdown(results, product=args.product, period=args.period)
        (out / "report.md").write_text(md, encoding="utf-8")
        (out / "report.html").write_text(to_html(md), encoding="utf-8")
        (out / "results.json").write_text(results_json(results), encoding="utf-8")

        print(f"Analysed {len(results)} parameter(s) over {len(df)} batch(es).")
        for r in results:
            print(f"  - {r.name}: {r.verdict}")
        print(f"Report written to {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
