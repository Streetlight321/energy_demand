"""Read-only Supabase queries used as pipeline checkpoints."""

from database.client import supabase

BRONZE_TABLE = "bronze_eia_region_data"


def get_latest_bronze_period(client=None):
    """Most recent `period` in Bronze, or None when Bronze is empty."""
    client = client or supabase

    response = (
        client
        .table(BRONZE_TABLE)
        .select("period")
        .order("period", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]["period"]
