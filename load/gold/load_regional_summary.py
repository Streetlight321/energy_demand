from load.records import DEFAULT_BATCH_SIZE
from load.gold.gold_writer import RESPONDENT_CONFLICT_KEY, upsert_gold

TABLE = "gold_regional_summary"


def load_gold_regional_summary(df, batch_size=DEFAULT_BATCH_SIZE):
    return upsert_gold(
        df,
        table=TABLE,
        conflict_key=RESPONDENT_CONFLICT_KEY,
        label="gold regional summary",
        batch_size=batch_size,
        timestamp_columns=("latest_period",),
    )
