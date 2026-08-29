"""Shared serialization + batched upsert used by every Silver/Gold loader.

Only database writes live here; nothing in this module transforms data.
"""

import numpy as np
import pandas as pd

from database.client import supabase
from database.retry import DEFAULT_ATTEMPTS, run_with_retry

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATE_FORMAT = "%Y-%m-%d"

DEFAULT_BATCH_SIZE = 250


def to_records(df, timestamp_columns=("period",), date_columns=()):
    """Turn a DataFrame into JSON/Postgres-safe records."""
    df = df.copy()

    for column in timestamp_columns:
        if column in df.columns:
            df[column] = (
                pd.to_datetime(df[column], utc=True, errors="coerce")
                .dt.strftime(TIMESTAMP_FORMAT)
            )

    for column in date_columns:
        if column in df.columns:
            df[column] = (
                pd.to_datetime(df[column], errors="coerce")
                .dt.strftime(DATE_FORMAT)
            )

    # inf / -inf are not valid JSON numbers.
    df = df.replace([np.inf, -np.inf], np.nan)

    # Critical: convert pandas NaN/NA to Python None so it becomes SQL NULL.
    df = df.astype(object).where(pd.notna(df), None)

    return df.to_dict(orient="records")


def upsert_batch(batch, table, conflict_key, client=None):
    """One upsert, retried on transient transport/gateway failures.

    Always an upsert on the table's conflict key, so replaying a batch that
    may have partially landed is safe.
    """
    client = client or supabase

    return (
        client
        .table(table)
        .upsert(batch, on_conflict=conflict_key)
        .execute()
    )


def upsert_records(
    df,
    table,
    conflict_key,
    label,
    batch_size=DEFAULT_BATCH_SIZE,
    timestamp_columns=("period",),
    date_columns=(),
    attempts=DEFAULT_ATTEMPTS,
    client=None,
):
    """Upsert a DataFrame in batches, printing concise progress."""
    records = to_records(
        df,
        timestamp_columns=timestamp_columns,
        date_columns=date_columns,
    )

    if not records:
        print(f"No {label} rows to load")
        return 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        last_row = min(i + batch_size, len(records))

        run_with_retry(
            lambda batch=batch: upsert_batch(
                batch, table, conflict_key, client=client
            ),
            description=f"{table} rows {i + 1}-{last_row}",
            attempts=attempts,
        )

        print(f"Loaded {last_row}/{len(records)} {label} rows")

    return len(records)
