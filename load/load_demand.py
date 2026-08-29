from load.records import DEFAULT_BATCH_SIZE
from load.silver_writer import upsert_silver

TABLE = "silver_demand"


def load_silver_demand(df, batch_size=DEFAULT_BATCH_SIZE):
    return upsert_silver(
        df,
        table=TABLE,
        label="demand",
        batch_size=batch_size,
    )
