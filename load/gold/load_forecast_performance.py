from load.gold.gold_writer import DAILY_CONFLICT_KEY, upsert_gold

TABLE = "gold_forecast_performance_daily"


def load_gold_forecast_performance_daily(df, batch_size=500):
    return upsert_gold(
        df,
        table=TABLE,
        conflict_key=DAILY_CONFLICT_KEY,
        label="gold forecast performance",
        batch_size=batch_size,
        timestamp_columns=(),
        date_columns=("date",),
    )
