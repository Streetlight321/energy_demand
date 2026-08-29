"""gold_demand_daily: daily demand shape per balancing authority."""

import pandas as pd

from transform.gold.common import (
    DAILY_KEY,
    add_calendar_date,
    attach_respondent_names,
    normalize_silver,
)
from transform.validation import (
    validate_business_key,
    validate_columns,
    validate_non_negative,
    validate_ordered,
)

TABLE = "gold_demand_daily"

REQUIRED_SILVER_COLUMNS = ["period", "respondent", "demand_mwh"]

GOLD_COLUMNS = [
    "date",
    "respondent",
    "respondent_name",
    "avg_demand_mwh",
    "peak_demand_mwh",
    "min_demand_mwh",
    "demand_stddev_mwh",
    "observation_count",
]


def transform_gold_demand_daily(df):
    """Aggregate `silver_demand` to one row per calendar date + respondent.

    Hourly demand is a rate, so the daily figures are mean / max / min rather
    than a sum, which would not be a meaningful "daily total".

    `demand_stddev_mwh` is the sample standard deviation and is therefore null
    for a date with a single observation.
    """
    df = normalize_silver(df, REQUIRED_SILVER_COLUMNS)

    if df.empty:
        return pd.DataFrame(columns=GOLD_COLUMNS)

    if "respondent_name" not in df.columns:
        df["respondent_name"] = pd.NA

    df = add_calendar_date(df)
    df["demand_mwh"] = pd.to_numeric(df["demand_mwh"], errors="coerce")

    daily = (
        df.groupby(DAILY_KEY, dropna=False)["demand_mwh"]
        .agg(
            avg_demand_mwh="mean",
            peak_demand_mwh="max",
            min_demand_mwh="min",
            demand_stddev_mwh="std",
            observation_count="count",
        )
        .reset_index()
    )

    daily["observation_count"] = daily["observation_count"].astype("int64")

    daily = attach_respondent_names(daily, df, DAILY_KEY)

    return (
        daily.loc[:, GOLD_COLUMNS]
        .sort_values(DAILY_KEY)
        .reset_index(drop=True)
    )


def validate_gold_demand_daily(df):
    validate_columns(df, TABLE, GOLD_COLUMNS)
    validate_business_key(df, TABLE, key=DAILY_KEY)
    validate_non_negative(df, TABLE, ["demand_stddev_mwh", "observation_count"])
    validate_ordered(df, TABLE, "peak_demand_mwh", "min_demand_mwh")

    return df
