from load.records import DEFAULT_BATCH_SIZE
from load.gold.gold_writer import HOURLY_CONFLICT_KEY, upsert_gold

TABLE = "gold_grid_balance_hourly"


def load_gold_grid_balance_hourly(df, batch_size=DEFAULT_BATCH_SIZE):
    return upsert_gold(
        df,
        table=TABLE,
        conflict_key=HOURLY_CONFLICT_KEY,
        label="gold grid balance",
        batch_size=batch_size,
        timestamp_columns=("period",),
    )
