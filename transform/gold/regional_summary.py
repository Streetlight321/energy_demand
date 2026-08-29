"""gold_regional_summary: one dashboard-ready row per balancing authority."""

import numpy as np
import pandas as pd

from transform.gold.common import HOURLY_KEY, RESPONDENT_KEY, normalize_silver
from transform.gold.grid_balance import transform_gold_grid_balance_hourly
from transform.validation import (
    validate_business_key,
    validate_columns,
    validate_non_negative,
)

TABLE = "gold_regional_summary"

# Forecast KPIs are averaged over the most recent 7 calendar days present in
# the forecast-performance frame, weighted by each day's observation count so
# a sparse day cannot swing the number.
RECENT_DAYS = 7

GOLD_COLUMNS = [
    "respondent",
    "respondent_name",
    "latest_period",
    "latest_demand_mwh",
    "latest_forecast_demand_mwh",
    "latest_net_generation_mwh",
    "latest_total_interchange_mwh",
    "recent_forecast_mape_pct",
    "recent_forecast_bias_mwh",
]

LATEST_COLUMNS = {
    "demand_mwh": "latest_demand_mwh",
    "net_generation_mwh": "latest_net_generation_mwh",
    "total_interchange_mwh": "latest_total_interchange_mwh",
}


def transform_gold_regional_summary(
    demand_df,
    generation_df,
    interchange_df,
    forecast_performance_df=None,
    recent_days=RECENT_DAYS,
):
    """Latest observed state plus recent forecast KPIs, one row per region.

    `latest_period` is the newest hour the region appears in, and every
    `latest_*` value is the measurement recorded *at that hour*. A metric the
    EIA had not published for that hour stays null rather than silently
    reaching back to an older, unrelated hour.

    `recent_forecast_*` summarise the last `recent_days` calendar days of
    `gold_forecast_performance_daily`, weighted by observation count.
    """
    balance = transform_gold_grid_balance_hourly(
        demand_df,
        generation_df,
        interchange_df,
    )

    if balance.empty:
        return pd.DataFrame(columns=GOLD_COLUMNS)

    latest_rows = balance.loc[
        balance.groupby("respondent")["period"].idxmax()
    ]

    summary = (
        latest_rows.rename(
            columns={"period": "latest_period", **LATEST_COLUMNS}
        )
        .loc[:, ["respondent", "respondent_name", "latest_period"]
             + list(LATEST_COLUMNS.values())]
        .reset_index(drop=True)
    )

    summary = summary.merge(
        _latest_forecast_demand(demand_df, latest_rows),
        on=RESPONDENT_KEY,
        how="left",
    )

    summary = summary.merge(
        _recent_forecast_kpis(forecast_performance_df, recent_days),
        on=RESPONDENT_KEY,
        how="left",
    )

    for column in GOLD_COLUMNS:
        if column not in summary.columns:
            summary[column] = np.nan

    return (
        summary.loc[:, GOLD_COLUMNS]
        .sort_values(RESPONDENT_KEY)
        .reset_index(drop=True)
    )


def _latest_forecast_demand(demand_df, latest_rows):
    """Day-ahead forecast recorded at each region's latest hour."""
    demand = normalize_silver(demand_df, ["period", "respondent"])

    if "forecast_demand_mwh" not in demand.columns:
        return pd.DataFrame(
            columns=RESPONDENT_KEY + ["latest_forecast_demand_mwh"]
        )

    anchors = latest_rows.loc[:, ["respondent", "period"]]

    return (
        anchors.merge(
            demand.loc[
                :, ["period", "respondent", "forecast_demand_mwh"]
            ].drop_duplicates(subset=HOURLY_KEY, keep="last"),
            on=HOURLY_KEY,
            how="left",
        )
        .rename(
            columns={"forecast_demand_mwh": "latest_forecast_demand_mwh"}
        )
        .loc[:, RESPONDENT_KEY + ["latest_forecast_demand_mwh"]]
    )


def _recent_forecast_kpis(forecast_performance_df, recent_days):
    """Observation-weighted MAPE and bias over the recent window."""
    empty = pd.DataFrame(
        columns=RESPONDENT_KEY
        + ["recent_forecast_mape_pct", "recent_forecast_bias_mwh"]
    )

    if forecast_performance_df is None or forecast_performance_df.empty:
        return empty

    performance = forecast_performance_df.copy()
    performance["date"] = pd.to_datetime(
        performance["date"], errors="coerce"
    )
    performance = performance.dropna(subset=["date"])

    if performance.empty:
        return empty

    cutoff = performance["date"].max() - pd.Timedelta(days=recent_days - 1)
    window = performance[performance["date"] >= cutoff]

    return (
        window.groupby("respondent")
        .apply(_weighted_kpis, include_groups=False)
        .reset_index()
    )


def _weighted_kpis(group):
    return pd.Series(
        {
            "recent_forecast_mape_pct": _weighted_mean(
                group["mape_pct"], group["observation_count"]
            ),
            "recent_forecast_bias_mwh": _weighted_mean(
                group["forecast_bias_mwh"], group["observation_count"]
            ),
        }
    )


def _weighted_mean(values, weights):
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce").fillna(0)

    usable = values.notna() & (weights > 0)
    total_weight = weights[usable].sum()

    if not usable.any() or total_weight == 0:
        return np.nan

    return float((values[usable] * weights[usable]).sum() / total_weight)


def validate_gold_regional_summary(df):
    validate_columns(df, TABLE, GOLD_COLUMNS)
    validate_business_key(df, TABLE, key=RESPONDENT_KEY)
    validate_non_negative(df, TABLE, ["recent_forecast_mape_pct"])

    return df
