"""Read-only Supabase queries: checkpoints and Gold input back-reads."""

import pandas as pd

from database.client import supabase
from database.retry import DEFAULT_ATTEMPTS, run_with_retry

BRONZE_TABLE = "bronze_eia_region_data"


def get_latest_bronze_period(client=None):
    """Most recent `period` in Bronze, or None when Bronze is empty.

    This is the first call of every scheduled run, so a single stalled
    connection should not fail the whole job.
    """
    client = client or supabase

    def read():
        return (
            client
            .table(BRONZE_TABLE)
            .select("period")
            .order("period", desc=True)
            .limit(1)
            .execute()
        )

    response = run_with_retry(read, description="Bronze checkpoint read")

    if not response.data:
        return None

    return response.data[0]["period"]


SILVER_DEMAND_TABLE = "silver_demand"

GOLD_FORECAST_PERFORMANCE_TABLE = "gold_forecast_performance_daily"

SILVER_DEMAND_COLUMNS = [
    "period",
    "respondent",
    "respondent_name",
    "demand_mwh",
    "forecast_demand_mwh",
    "forecast_error_mwh",
    "forecast_error_pct",
]

FORECAST_PERFORMANCE_COLUMNS = [
    "date",
    "respondent",
    "respondent_name",
    "mape_pct",
    "forecast_bias_mwh",
    "observation_count",
]

PAGE_SIZE = 1000


def _execute_page(query_factory, offset, page_size):
    """One page, retried on transient failures by the shared helper."""
    def read():
        return (
            query_factory()
            .range(offset, offset + page_size - 1)
            .execute()
            .data
        )

    return run_with_retry(
        read,
        description=f"read at offset {offset}",
        attempts=DEFAULT_ATTEMPTS,
    )


def _fetch_all(query_factory, page_size=PAGE_SIZE):
    """Page through a PostgREST query, which caps rows per response."""
    rows = []
    offset = 0

    while True:
        page = _execute_page(query_factory, offset, page_size)

        if not page:
            break

        rows.extend(page)

        if len(page) < page_size:
            break

        offset += page_size

    return pd.DataFrame(rows)


def fetch_silver_demand(start, end=None, client=None):
    """Silver demand rows in [start, end).

    Used to complete the partial first calendar day of an ingestion window so
    daily Gold aggregates are never computed from half a day.
    """
    client = client or supabase

    def query():
        builder = (
            client
            .table(SILVER_DEMAND_TABLE)
            .select(",".join(SILVER_DEMAND_COLUMNS))
            .gte("period", _iso(start))
            .order("period")
        )

        if end is not None:
            builder = builder.lt("period", _iso(end))

        return builder

    frame = _fetch_all(query)

    if frame.empty:
        return pd.DataFrame(columns=SILVER_DEMAND_COLUMNS)

    return frame


def fetch_recent_forecast_performance(start_date, client=None):
    """Daily forecast-performance rows from `start_date` onwards."""
    client = client or supabase

    def query():
        return (
            client
            .table(GOLD_FORECAST_PERFORMANCE_TABLE)
            .select(",".join(FORECAST_PERFORMANCE_COLUMNS))
            .gte("date", _date_string(start_date))
            .order("date")
        )

    frame = _fetch_all(query)

    if frame.empty:
        return pd.DataFrame(columns=FORECAST_PERFORMANCE_COLUMNS)

    return frame


def _iso(value):
    return pd.Timestamp(value).tz_convert("UTC").strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _date_string(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")
