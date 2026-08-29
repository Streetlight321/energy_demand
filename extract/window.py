"""Ingestion window helpers (pure time arithmetic, no I/O)."""

import pandas as pd

# The EIA hourly API expects periods like "2026-08-27T12".
EIA_PERIOD_FORMAT = "%Y-%m-%dT%H"

LOOKBACK_HOURS = 48

# A scheduled run should never try to swallow years of history in one go: if
# Bronze is far behind, each run ingests a bounded catch-up window and the
# next run picks up where it left off.
MAX_CATCHUP_HOURS = 24 * 7


def calculate_ingestion_start(latest_period, lookback_hours=LOOKBACK_HOURS):
    """Latest Bronze period minus a sliding lookback, EIA-formatted.

    The lookback is deliberate: the EIA revises recent hours and backfills
    late-arriving records, so every run re-reads the trailing window instead
    of starting at `latest + 1 hour`.

    Returns None when there is no checkpoint yet.
    """
    if latest_period is None:
        return None

    parsed = pd.to_datetime(latest_period, utc=True, errors="coerce")

    if pd.isna(parsed):
        raise ValueError(
            f"Could not parse latest Bronze period: {latest_period!r}"
        )

    start = parsed - pd.Timedelta(hours=lookback_hours)

    return start.strftime(EIA_PERIOD_FORMAT)


def format_period(timestamp):
    """Format any timestamp-like value for the EIA API."""
    parsed = pd.to_datetime(timestamp, utc=True, errors="coerce")

    if pd.isna(parsed):
        raise ValueError(f"Could not parse period: {timestamp!r}")

    return parsed.strftime(EIA_PERIOD_FORMAT)


def calculate_ingestion_end(start, max_window_hours=MAX_CATCHUP_HOURS):
    """Cap a run's window, or None when `start` is already close to now.

    Returning None keeps the normal hourly run unbounded-to-present, which is
    what the 48-hour lookback wants. It only kicks in when the checkpoint is
    stale enough that a single run would be unreasonably large.
    """
    if start is None:
        return None

    parsed = pd.to_datetime(start, utc=True, errors="coerce")

    if pd.isna(parsed):
        raise ValueError(f"Could not parse ingestion start: {start!r}")

    limit = parsed + pd.Timedelta(hours=max_window_hours)

    if limit >= pd.Timestamp.now(tz="UTC"):
        return None

    return limit.strftime(EIA_PERIOD_FORMAT)
