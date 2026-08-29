"""Write path for the Gold tables: serialization and batched upserts only."""

from load.records import DEFAULT_BATCH_SIZE, upsert_records

DAILY_CONFLICT_KEY = "date,respondent"
HOURLY_CONFLICT_KEY = "period,respondent"
RESPONDENT_CONFLICT_KEY = "respondent"


def upsert_gold(
    df,
    table,
    conflict_key,
    label,
    batch_size=DEFAULT_BATCH_SIZE,
    timestamp_columns=("period",),
    date_columns=(),
):
    return upsert_records(
        df,
        table=table,
        conflict_key=conflict_key,
        label=label,
        batch_size=batch_size,
        timestamp_columns=timestamp_columns,
        date_columns=date_columns,
    )
