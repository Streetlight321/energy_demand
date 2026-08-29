"""Shared write path for the Silver tables.

All three Silver tables share the same (period, respondent) grain, so they
share one batched upsert helper. Only database writes live here.
"""

import numpy as np
import pandas as pd

from database.client import supabase

CONFLICT_KEY = "period,respondent"


def to_records(df):
    """Turn a Silver DataFrame into JSON/Postgres-safe records."""
    df = df.copy()

    # Postgres-friendly ISO timestamp.
    df["period"] = (
        pd.to_datetime(
            df["period"],
            utc=True,
            errors="coerce",
        )
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    # inf / -inf are not valid JSON numbers.
    df = df.replace([np.inf, -np.inf], np.nan)

    # Critical: convert pandas NaN/NA to Python None so it becomes SQL NULL.
    df = df.astype(object).where(pd.notna(df), None)

    return df.to_dict(orient="records")


def upsert_silver(df, table, label, batch_size=500):
    """Upsert a Silver DataFrame in batches, printing progress."""
    records = to_records(df)

    if not records:
        print(f"No {label} rows to load")
        return 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        (
            supabase
            .table(table)
            .upsert(
                batch,
                on_conflict=CONFLICT_KEY,
            )
            .execute()
        )

        print(
            f"Loaded "
            f"{min(i + batch_size, len(records))}"
            f"/{len(records)} {label} rows"
        )

    return len(records)
