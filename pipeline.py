"""Production orchestration: checkpoint -> extract -> Bronze -> Silver -> Gold.

Scheduled runs (GitHub Actions, or `uv run pipeline.py`) ingest a trailing
window anchored on the latest Bronze period. Historical loads go through
`scripts/backfill.py`, which reuses `ingest_window` below.
"""

import pandas as pd

from database.queries import (
    fetch_recent_forecast_performance,
    fetch_silver_demand,
    get_latest_bronze_period,
)
from extract.pull_data import pull_raw
from extract.window import (
    LOOKBACK_HOURS,
    MAX_CATCHUP_HOURS,
    calculate_ingestion_end,
    calculate_ingestion_start,
)
from load.load_bronze import load_bronze
from load.load_demand import load_silver_demand
from load.load_generation import load_silver_generation
from load.gold.load_demand_daily import load_gold_demand_daily
from load.gold.load_forecast_performance import (
    load_gold_forecast_performance_daily,
)
from load.gold.load_grid_balance import load_gold_grid_balance_hourly
from load.gold.load_regional_summary import load_gold_regional_summary
from load.load_interchange import load_silver_interchange
from transform.demand import transform_demand, validate_demand
from transform.generation import (
    transform_generation,
    validate_generation,
)
from transform.gold.demand_daily import (
    transform_gold_demand_daily,
    validate_gold_demand_daily,
)
from transform.gold.forecast_performance import (
    transform_gold_forecast_performance_daily,
    validate_gold_forecast_performance_daily,
)
from transform.gold.grid_balance import (
    transform_gold_grid_balance_hourly,
    validate_gold_grid_balance_hourly,
)
from transform.gold.regional_summary import (
    RECENT_DAYS,
    transform_gold_regional_summary,
    validate_gold_regional_summary,
)
from transform.interchange import (
    transform_interchange,
    validate_interchange,
)

EMPTY_BRONZE_MESSAGE = (
    "Bronze table is empty. Run the historical backfill before scheduled "
    "ingestion: uv run scripts/backfill.py"
)


def ingest_window(start=None, end=None):
    """Ingest one EIA window end to end. Idempotent: every write is an upsert.

    The API is called exactly once; all three Silver domains reuse that frame.
    """
    print(f"Extracting EIA data from {start or 'the start of the dataset'}...")
    raw_df = pull_raw(start=start, end=end)
    print(f"Extracted {len(raw_df)} rows")

    if raw_df.empty:
        print("No EIA records returned.")
        return {
            "rows_extracted": 0,
            "demand_rows": 0,
            "generation_rows": 0,
            "interchange_rows": 0,
        }

    # Bronze: source-oriented long format, grain (period, respondent, type).
    print("Loading Bronze...")
    load_bronze(raw_df)

    # Silver: one domain table per metric family, grain (period, respondent).
    print("Transforming Silver demand...")
    demand_df = validate_demand(transform_demand(raw_df))
    load_silver_demand(demand_df)

    print("Transforming Silver generation...")
    generation_df = validate_generation(transform_generation(raw_df))
    load_silver_generation(generation_df)

    print("Transforming Silver interchange...")
    interchange_df = validate_interchange(transform_interchange(raw_df))
    load_silver_interchange(interchange_df)

    gold_counts = run_gold(demand_df, generation_df, interchange_df)

    return {
        "rows_extracted": len(raw_df),
        "demand_rows": len(demand_df),
        "generation_rows": len(generation_df),
        "interchange_rows": len(interchange_df),
        **gold_counts,
    }


def run_gold(demand_df, generation_df, interchange_df):
    """Recompute only the Gold rows the current Silver window touches.

    Hourly Gold (grid balance) is derived straight from the Silver frames the
    run just produced. Daily Gold is keyed by calendar date, so the first day
    of the window is completed from Supabase first - otherwise a window that
    starts mid-day would overwrite a full day's aggregate with a partial one.
    """
    daily_source = complete_partial_first_day(demand_df)

    print("Transforming Gold demand daily...")
    demand_daily_df = validate_gold_demand_daily(
        transform_gold_demand_daily(daily_source)
    )
    load_gold_demand_daily(demand_daily_df)

    print("Transforming Gold forecast performance...")
    forecast_df = validate_gold_forecast_performance_daily(
        transform_gold_forecast_performance_daily(daily_source)
    )
    load_gold_forecast_performance_daily(forecast_df)

    print("Transforming Gold grid balance...")
    balance_df = validate_gold_grid_balance_hourly(
        transform_gold_grid_balance_hourly(
            demand_df,
            generation_df,
            interchange_df,
        )
    )
    load_gold_grid_balance_hourly(balance_df)

    print("Transforming Gold regional summary...")
    summary_df = validate_gold_regional_summary(
        transform_gold_regional_summary(
            demand_df,
            generation_df,
            interchange_df,
            forecast_performance_df=recent_forecast_performance(forecast_df),
        )
    )
    load_gold_regional_summary(summary_df)

    return {
        "gold_demand_daily_rows": len(demand_daily_df),
        "gold_forecast_performance_rows": len(forecast_df),
        "gold_grid_balance_rows": len(balance_df),
        "gold_regional_summary_rows": len(summary_df),
    }


def complete_partial_first_day(demand_df, fetch=None):
    """Prepend the hours of the window's first calendar day it does not cover.

    The trailing edge of the window is intentionally left partial: today is
    still accumulating and the next run recomputes it.
    """
    if demand_df.empty:
        return demand_df

    fetch = fetch or fetch_silver_demand
    window_start = pd.to_datetime(demand_df["period"], utc=True).min()
    day_start = window_start.floor("D")

    if day_start >= window_start:
        return demand_df

    print(
        f"Completing the partial first day: reading Silver demand "
        f"{day_start:%Y-%m-%dT%H} -> {window_start:%Y-%m-%dT%H}"
    )

    head = fetch(start=day_start, end=window_start)

    if head.empty:
        return demand_df

    head["period"] = pd.to_datetime(head["period"], utc=True)

    return (
        pd.concat([head, demand_df], ignore_index=True)
        .drop_duplicates(subset=["period", "respondent"], keep="last")
        .reset_index(drop=True)
    )


def recent_forecast_performance(
    forecast_df,
    recent_days=RECENT_DAYS,
    fetch=None,
):
    """Read back the recent daily forecast metrics for the summary KPIs.

    The freshly computed rows are already loaded, so this picks up history
    beyond the current window as well.
    """
    if forecast_df.empty:
        return forecast_df

    fetch = fetch or fetch_recent_forecast_performance
    latest_date = pd.to_datetime(forecast_df["date"]).max()
    start_date = latest_date - pd.Timedelta(days=recent_days - 1)

    return fetch(start_date=start_date)


def run_pipeline(
    lookback_hours=LOOKBACK_HOURS,
    max_window_hours=MAX_CATCHUP_HOURS,
):
    """Hourly incremental run."""
    print("Finding latest Bronze timestamp...")
    latest_period = get_latest_bronze_period()

    if latest_period is None:
        raise RuntimeError(EMPTY_BRONZE_MESSAGE)

    start = calculate_ingestion_start(
        latest_period,
        lookback_hours=lookback_hours,
    )

    print(
        f"Latest Bronze period: {latest_period} "
        f"(re-reading the last {lookback_hours}h from {start})"
    )

    end = calculate_ingestion_end(
        start,
        max_window_hours=max_window_hours,
    )

    if end:
        print(
            f"Bronze is more than {max_window_hours}h behind; this run is "
            f"capped at {end}. Re-run to keep catching up, or use "
            f"scripts/backfill.py for a large gap."
        )

    counts = ingest_window(start=start, end=end)

    print("Pipeline complete.")

    return counts


if __name__ == "__main__":
    run_pipeline()
