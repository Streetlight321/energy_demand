import os

from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL not found")

if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY not found")


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


def load_bronze(df):
    df = df.copy()

    df = df.rename(
        columns={
            "respondent-name": "respondent_name",
            "type-name": "type_name",
            "value-units": "value_units",
        }
    )

    records = df.to_dict(orient="records")

    response = (
        supabase
        .table("bronze_eia_region_data")
        .upsert(
            records,
            on_conflict="period,respondent,type"
        )
        .execute()
    )

    return response