import os

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