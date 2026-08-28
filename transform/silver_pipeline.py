import pandas as pd

def bronze_to_silver(df):
    df = df.copy()

    # 1. Standardize datatypes
    df["period"] = pd.to_datetime(
        df["period"],
        utc=True,
        errors="coerce"
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    # 2. Keep only expected EIA metrics
    valid_types = ["D", "DF", "NG", "TI"]

    df = df[
        df["type"].isin(valid_types)
    ]

    # 3. Convert long metric rows into one row per
    #    period + balancing authority
    silver = (
        df.pivot_table(
            index=[
                "period",
                "respondent",
                "respondent_name"
            ],
            columns="type",
            values="value",
            aggfunc="first"
        )
        .reset_index()
    )

    silver.columns.name = None

    # 4. Rename EIA codes to analytical names
    silver = silver.rename(
        columns={
            "D": "demand_mwh",
            "DF": "forecast_demand_mwh",
            "NG": "net_generation_mwh",
            "TI": "total_interchange_mwh",
        }
    )

    # 5. Forecast error
    silver["forecast_error_mwh"] = (
        silver["demand_mwh"]
        - silver["forecast_demand_mwh"]
    )

    silver["forecast_error_pct"] = (
        silver["forecast_error_mwh"]
        / silver["demand_mwh"]
        * 100
    )

    # Avoid division-by-zero infinities
    silver["forecast_error_pct"] = (
        silver["forecast_error_pct"]
        .replace([float("inf"), float("-inf")], pd.NA)
    )

    return silver