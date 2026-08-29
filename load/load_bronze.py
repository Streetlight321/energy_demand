"""Bronze writes: source-oriented rows, keyed by period + respondent + type."""

import pandas as pd

from database.retry import DEFAULT_ATTEMPTS
from load.records import upsert_records

TABLE = "bronze_eia_region_data"

CONFLICT_KEY = "period,respondent,type"

# Smaller batches than Silver/Gold: Bronze is the widest table and the one a
# multi-year backfill hammers hardest, and smaller requests stall less often.
BRONZE_BATCH_SIZE = 250

RAW_COLUMN_RENAMES = {
    "respondent-name": "respondent_name",
    "type-name": "type_name",
    "value-units": "value_units",
}


def load_bronze(df, batch_size=BRONZE_BATCH_SIZE, attempts=DEFAULT_ATTEMPTS):
    """Upsert raw EIA rows into Bronze, unchanged apart from column names."""
    df = df.copy()

    df = df.rename(columns=RAW_COLUMN_RENAMES)

    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # Serialization, batching and retry are shared with the Silver/Gold path.
    return upsert_records(
        df,
        table=TABLE,
        conflict_key=CONFLICT_KEY,
        label="Bronze",
        batch_size=batch_size,
        attempts=attempts,
    )
