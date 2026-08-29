from load.records import DEFAULT_BATCH_SIZE
from load.silver_writer import upsert_silver

TABLE = "silver_interchange"


def load_silver_interchange(df, batch_size=DEFAULT_BATCH_SIZE):
    return upsert_silver(
        df,
        table=TABLE,
        label="interchange",
        batch_size=batch_size,
    )
