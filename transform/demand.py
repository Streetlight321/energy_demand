"""Silver demand transformation: EIA `D` + `DF` -> one row per hour/region."""

import numpy as np
import pandas as pd

from transform.common import (
    BUSINESS_KEY,
    normalize_raw,
    replace_infinities,
)
from transform.validation import (
    validate_business_key,
    validate_columns,
    warn_negative_values,
)

TABLE = "silver_demand"

METRIC_COLUMNS = {
    "D": "demand_mwh",
    "DF": "forecast_demand_mwh",
}

DEMAND_COLUMNS = [
    "period",
    "respondent",
    "respondent_name",
    "demand_mwh",
    "forecast_demand_mwh",
    "forecast_error_mwh",
    "forecast_error_pct",
]


def transform_demand(df):
    """Pivot actual (`D`) and day-ahead forecast (`DF`) demand side by side.

    Pure function: DataFrame -> DataFrame.
    """
    df = normalize_raw(df)

    demand = df[df["type"].isin(METRIC_COLUMNS)]

    if demand.empty:
        return pd.DataFrame(columns=DEMAND_COLUMNS)

    pivoted = (
        demand.pivot_table(
            index=BUSINESS_KEY,
            columns="type",
            values="value",
            aggfunc="first",
            dropna=False,
        )
        .reset_index()
    )

    pivoted.columns.name = None

    for metric, column in METRIC_COLUMNS.items():
        if metric in pivoted.columns:
            pivoted = pivoted.rename(columns={metric: column})
        else:
            # The window may legitimately contain only one of the two metrics.
            pivoted[column] = np.nan

    pivoted = pivoted.merge(
        _respondent_names(demand),
        on=BUSINESS_KEY,
        how="left",
    )

    pivoted["forecast_error_mwh"] = (
        pivoted["demand_mwh"] - pivoted["forecast_demand_mwh"]
    )

    # A percentage is only meaningful against a positive baseline: zero would
    # be infinite and a negative actual would flip the sign of the error.
    # The signed error in MWh is still reported for those rows.
    denominator = pivoted["demand_mwh"].where(pivoted["demand_mwh"] > 0)

    pivoted["forecast_error_pct"] = replace_infinities(
        pivoted["forecast_error_mwh"] / denominator * 100
    )

    return (
        pivoted.loc[:, DEMAND_COLUMNS]
        .sort_values(BUSINESS_KEY)
        .reset_index(drop=True)
    )


def _respondent_names(demand):
    """First non-null respondent name per (period, respondent)."""
    names = (
        demand.loc[:, BUSINESS_KEY + ["respondent_name"]]
        .dropna(subset=["respondent_name"])
        .drop_duplicates(subset=BUSINESS_KEY, keep="first")
    )

    if names.empty:
        names = pd.DataFrame(
            columns=BUSINESS_KEY + ["respondent_name"]
        ).astype(demand.loc[:, BUSINESS_KEY + ["respondent_name"]].dtypes)

    return names


def validate_demand(df):
    """Structural checks for `silver_demand`."""
    validate_columns(df, TABLE, DEMAND_COLUMNS)
    validate_business_key(df, TABLE)

    # Non-structural: reported, never fatal.
    warn_negative_values(df, TABLE, "demand_mwh")

    return df
