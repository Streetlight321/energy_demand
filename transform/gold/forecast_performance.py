"""gold_forecast_performance_daily: day-ahead forecast accuracy per region."""

import numpy as np
import pandas as pd

from transform.common import replace_infinities
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
)

TABLE = "gold_forecast_performance_daily"

REQUIRED_SILVER_COLUMNS = [
    "period",
    "respondent",
    "demand_mwh",
    "forecast_demand_mwh",
]

GOLD_COLUMNS = [
    "date",
    "respondent",
    "respondent_name",
    "mae_mwh",
    "rmse_mwh",
    "mape_pct",
    "forecast_bias_mwh",
    "max_abs_error_mwh",
    "observation_count",
]


def transform_gold_forecast_performance_daily(df):
    """Recompute forecast error metrics from actual and forecast demand.

    Metrics are derived from the raw pair, not by averaging Silver's
    `forecast_error_pct`, so a single bad hour cannot distort the daily
    figures through a pre-divided percentage.

    A row is usable when both actual and forecast demand are present;
    `observation_count` counts exactly those rows. MAPE additionally excludes
    zero-demand hours, where the ratio is undefined.
    """
    df = normalize_silver(df, REQUIRED_SILVER_COLUMNS)

    if df.empty:
        return pd.DataFrame(columns=GOLD_COLUMNS)

    if "respondent_name" not in df.columns:
        df["respondent_name"] = pd.NA

    df = add_calendar_date(df)

    actual = pd.to_numeric(df["demand_mwh"], errors="coerce")
    forecast = pd.to_numeric(df["forecast_demand_mwh"], errors="coerce")

    # Signed, actual minus forecast: positive means demand exceeded forecast.
    df["_error"] = actual - forecast
    df["_abs_error"] = df["_error"].abs()
    df["_squared_error"] = df["_error"] ** 2

    # Undefined against a zero baseline, so those hours are excluded.
    ratio = df["_abs_error"] / actual.abs()
    df["_abs_pct_error"] = replace_infinities(
        ratio.where(actual.notna() & (actual != 0))
    )

    grouped = df.groupby(DAILY_KEY, dropna=False)

    performance = grouped.agg(
        mae_mwh=("_abs_error", "mean"),
        rmse_mwh=("_squared_error", "mean"),
        mape_pct=("_abs_pct_error", "mean"),
        forecast_bias_mwh=("_error", "mean"),
        max_abs_error_mwh=("_abs_error", "max"),
        observation_count=("_error", "count"),
    ).reset_index()

    performance["rmse_mwh"] = np.sqrt(performance["rmse_mwh"])
    performance["mape_pct"] = performance["mape_pct"] * 100
    performance["observation_count"] = (
        performance["observation_count"].astype("int64")
    )

    performance = attach_respondent_names(performance, df, DAILY_KEY)

    return (
        performance.loc[:, GOLD_COLUMNS]
        .sort_values(DAILY_KEY)
        .reset_index(drop=True)
    )


def validate_gold_forecast_performance_daily(df):
    validate_columns(df, TABLE, GOLD_COLUMNS)
    validate_business_key(df, TABLE, key=DAILY_KEY)
    validate_non_negative(
        df,
        TABLE,
        ["mae_mwh", "rmse_mwh", "mape_pct", "max_abs_error_mwh",
         "observation_count"],
    )

    return df
