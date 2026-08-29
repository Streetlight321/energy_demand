"""Manual historical backfill. Never run automatically by the scheduler.

    uv run scripts/backfill.py
    uv run scripts/backfill.py --start 2024-01-01T00 --end 2024-06-30T23
    uv run scripts/backfill.py --chunk-days 7

The window is walked in chunks so a multi-year load does not have to fit in
one API response or one DataFrame. Every write is an upsert, so re-running a
chunk is safe.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extract.window import format_period  # noqa: E402
from pipeline import ingest_window  # noqa: E402

# EIA hourly region data begins in mid-2018; this is a safe historical floor.
DEFAULT_START = "2019-01-01T00"

DEFAULT_CHUNK_DAYS = 30


def iter_windows(start, end, chunk_days):
    """Yield (start, end) EIA period strings covering [start, end]."""
    cursor = pd.to_datetime(start, utc=True)
    stop = pd.to_datetime(end, utc=True)

    if pd.isna(cursor) or pd.isna(stop):
        raise ValueError(f"Could not parse backfill window: {start} -> {end}")

    if cursor > stop:
        raise ValueError(f"Backfill start {start} is after end {end}")

    step = pd.Timedelta(days=chunk_days)

    while cursor <= stop:
        chunk_end = min(cursor + step, stop)

        yield format_period(cursor), format_period(chunk_end)

        cursor = chunk_end + pd.Timedelta(hours=1)


def run_backfill(start, end, chunk_days=DEFAULT_CHUNK_DAYS):
    total = 0

    for window_start, window_end in iter_windows(start, end, chunk_days):
        print(f"\n=== Backfilling {window_start} -> {window_end} ===")

        counts = ingest_window(start=window_start, end=window_end)
        total += counts["rows_extracted"]

    print(f"\nBackfill complete. {total} raw rows ingested.")

    return total


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Historical EIA backfill into Bronze and Silver.",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help=f"EIA period to start from (default: {DEFAULT_START})",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="EIA period to stop at (default: now, UTC)",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=DEFAULT_CHUNK_DAYS,
        help=f"Days per request window (default: {DEFAULT_CHUNK_DAYS})",
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    end = args.end or format_period(pd.Timestamp.now(tz="UTC"))

    print(
        f"Backfilling {args.start} -> {end} "
        f"in {args.chunk_days}-day chunks"
    )

    run_backfill(args.start, end, chunk_days=args.chunk_days)


if __name__ == "__main__":
    main()
