import pandas as pd
from database.client import supabase


def load_silver(df, batch_size=500):
    df = df.copy()

    # Convert timestamp to JSON/Postgres-friendly ISO format
    df["period"] = (
        pd.to_datetime(df["period"], utc=True)
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    # Convert pandas NaN / NA into Python None
    # so Supabase receives SQL NULL
    df = df.astype(object).where(
        pd.notna(df),
        None
    )

    records = df.to_dict(orient="records")

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        (
            supabase
            .table("silver_region_hourly")
            .upsert(
                batch,
                on_conflict="period,respondent"
            )
            .execute()
        )

        print(
            f"Loaded "
            f"{min(i + batch_size, len(records))}"
            f"/{len(records)} Silver rows"
        )