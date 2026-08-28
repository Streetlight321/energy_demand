import pandas as pd
from database.client import supabase


def load_bronze(df, batch_size=500):
    """
    Upsert an already-transformed dataframe into bronze_eia_region_data.
    Expects df to already be in bronze shape (see transform/to_bronze.py).
    """
    records = df.to_dict(orient="records")

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        (
            supabase
            .table("bronze_eia_region_data")
            .upsert(
                batch,
                on_conflict="period,respondent,type"
            )
            .execute()
        )

        print(
            f"Loaded "
            f"{min(i + batch_size, len(records))}"
            f"/{len(records)} rows"
        )