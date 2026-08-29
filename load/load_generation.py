from load.silver_writer import upsert_silver

TABLE = "silver_generation"


def load_silver_generation(df, batch_size=500):
    return upsert_silver(
        df,
        table=TABLE,
        label="generation",
        batch_size=batch_size,
    )
