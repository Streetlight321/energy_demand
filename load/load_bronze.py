import pandas as pd

from database.client import supabase


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
        pd.to_datetime(
            df["period"],
            utc=True,
            errors="coerce"
        )
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    # Critical: convert pandas NaN/NA to Python None
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
            f"/{len(records)} Bronze rows"
        )