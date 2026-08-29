from load.records import DEFAULT_BATCH_SIZE
from load.gold.gold_writer import DAILY_CONFLICT_KEY, upsert_gold

TABLE = "gold_demand_daily"


def load_gold_demand_daily(df, batch_size=DEFAULT_BATCH_SIZE):
    return upsert_gold(
        df,
        table=TABLE,
        conflict_key=DAILY_CONFLICT_KEY,
        label="gold demand daily",
        batch_size=batch_size,
        timestamp_columns=(),
        date_columns=("date",),
    )
