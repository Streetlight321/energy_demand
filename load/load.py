import os
import pandas as pd

from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL not found in environment")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY not found in environment")


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


def load_bronze(df, batch_size=500):
    df = df.copy()

    df = df.rename(
        columns={
            "respondent-name": "respondent_name",
            "type-name": "type_name",
            "value-units": "value_units",
        }
    )

    df["period"] = (
        pd.to_datetime(df["period"], utc=True)
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    # Convert NaN/NA to None so it becomes SQL NULL
    df = df.astype(object).where(
        pd.notna(df),
        None
    )

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