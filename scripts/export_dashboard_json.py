"""Export Gold (and Silver demand) to the static JSON the portfolio reads.

    uv run scripts/export_dashboard_json.py \
        --out ../YousefEddinPortfolio/energy-dashboard/data \
        --days 90

Read-only against Supabase. The output contains aggregates only - no
credentials, no connection strings - which is why the dashboard can be a
plain static page.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from database.client import supabase  # noqa: E402
from database.queries import _fetch_all  # noqa: E402

DEFAULT_DAYS = 90

# dataset -> (table, columns, date-ish column used for the window)
EXPORTS = {
    "regional_summary": (
        "gold_regional_summary",
        [
            "respondent", "respondent_name", "latest_period",
            "latest_demand_mwh", "latest_forecast_demand_mwh",
            "latest_net_generation_mwh", "latest_total_interchange_mwh",
            "recent_forecast_mape_pct", "recent_forecast_bias_mwh",
        ],
        None,
    ),
    "demand_daily": (
        "gold_demand_daily",
        [
            "date", "respondent", "respondent_name", "avg_demand_mwh",
            "peak_demand_mwh", "min_demand_mwh", "demand_stddev_mwh",
            "observation_count",
        ],
        "date",
    ),
    "demand_hourly": (
        "silver_demand",
        ["period", "respondent", "demand_mwh", "forecast_demand_mwh"],
        "period",
    ),
    "forecast_performance": (
        "gold_forecast_performance_daily",
        [
            "date", "respondent", "respondent_name", "mae_mwh", "rmse_mwh",
            "mape_pct", "forecast_bias_mwh", "max_abs_error_mwh",
            "observation_count",
        ],
        "date",
    ),
    "grid_balance": (
        "gold_grid_balance_hourly",
        [
            "period", "respondent", "demand_mwh", "net_generation_mwh",
            "total_interchange_mwh", "generation_minus_demand_mwh",
        ],
        "period",
    ),
}


def fetch(table, columns, window_column, since):
    def query():
        builder = supabase.table(table).select(",".join(columns))

        if window_column and since:
            builder = builder.gte(window_column, since).order(window_column)

        return builder

    frame = _fetch_all(query)

    if frame.empty:
        return []

    return to_json_records(frame)


def to_json_records(frame):
    """JSON has no NaN/Infinity literal - missing measurements become null."""
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.astype(object).where(pd.notna(frame), None)

    records = frame.to_dict(orient="records")

    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and not math.isfinite(value):
                record[key] = None

    return records


def export(out_dir, days):
    out_dir.mkdir(parents=True, exist_ok=True)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for name, (table, columns, window_column) in EXPORTS.items():
        since = None

        if window_column == "date":
            since = cutoff.strftime("%Y-%m-%d")
        elif window_column == "period":
            since = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        rows = fetch(table, columns, window_column, since)

        payload = {
            "meta": {
                "dataset": name,
                "source": "gold_export",
                "table": table,
                "generated_at": generated_at,
                "window_days": days if window_column else None,
                "row_count": len(rows),
            },
            "rows": rows,
        }

        path = out_dir / f"{name}.json"
        # allow_nan=False turns a stray NaN into a loud failure rather than
        # a file the browser silently rejects.
        path.write_text(
            json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n"
        )

        size_kb = path.stat().st_size / 1024
        print(f"{path.name}: {len(rows)} rows from {table} ({size_kb:.0f} KB)")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Export Gold tables to the dashboard's static JSON.",
    )
    parser.add_argument(
        "--out",
        default="../YousefEddinPortfolio/energy-dashboard/data",
        help="directory to write the JSON files into",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"how much history to export (default: {DEFAULT_DAYS})",
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    out_dir = Path(args.out).expanduser().resolve()

    print(f"Exporting the last {args.days} days to {out_dir}")
    export(out_dir, args.days)
    print("Done. Reload the dashboard; the sample-data banner will disappear.")


if __name__ == "__main__":
    main()
