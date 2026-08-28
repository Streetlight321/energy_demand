import pandas as pd

def to_bronze_pipe(df):
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
    return df