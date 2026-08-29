"""Write path for the Silver tables.

All three Silver tables share the same (period, respondent) grain, so they
share one batched upsert helper.
"""

from load.records import to_records, upsert_records

CONFLICT_KEY = "period,respondent"

__all__ = ["CONFLICT_KEY", "to_records", "upsert_silver"]


def upsert_silver(df, table, label, batch_size=500):
    """Upsert a Silver DataFrame in batches, printing progress."""
    return upsert_records(
        df,
        table=table,
        conflict_key=CONFLICT_KEY,
        label=label,
        batch_size=batch_size,
    )
