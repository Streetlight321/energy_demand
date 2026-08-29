"""Production orchestration: checkpoint -> extract -> Bronze -> Silver.

Scheduled runs (GitHub Actions, or `uv run pipeline.py`) ingest a trailing
window anchored on the latest Bronze period. Historical loads go through
`scripts/backfill.py`, which reuses `ingest_window` below.
"""

from database.queries import get_latest_bronze_period
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
from load.load_interchange import load_silver_interchange
from transform.demand import transform_demand, validate_demand
from transform.generation import (
    transform_generation,
    validate_generation,
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

    return {
        "rows_extracted": len(raw_df),
        "demand_rows": len(demand_df),
        "generation_rows": len(generation_df),
        "interchange_rows": len(interchange_df),
    }


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
