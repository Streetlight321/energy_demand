"""Shared helpers for the Bronze -> Silver transformations.

Everything in here is pure: a DataFrame goes in, a DataFrame comes out.
No EIA API calls, no Supabase access, no loading.
"""

import numpy as np
import pandas as pd

# Raw EIA payloads use hyphenated column names.
RAW_COLUMN_RENAMES = {
    "respondent-name": "respondent_name",
    "type-name": "type_name",
    "value-units": "value_units",
}

REQUIRED_RAW_COLUMNS = ["period", "respondent", "type", "value"]

BUSINESS_KEY = ["period", "respondent"]


def normalize_raw(df):
    """Rename raw EIA columns and standardize `period` / `value` dtypes."""
    df = df.copy()

    df = df.rename(columns=RAW_COLUMN_RENAMES)

    missing = [
        column
        for column in REQUIRED_RAW_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Raw EIA frame is missing required column(s): {missing}. "
            f"Got: {sorted(df.columns)}"
        )

    if "respondent_name" not in df.columns:
        df["respondent_name"] = pd.NA

    df["period"] = pd.to_datetime(
        df["period"],
        utc=True,
        errors="coerce",
    )

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    return df


def select_metric(df, metric, value_column):
    """Filter to one EIA `type` code and rename `value` to a domain column."""
    selected = (
        df[df["type"] == metric]
        .loc[:, ["period", "respondent", "respondent_name", "value"]]
        .rename(columns={"value": value_column})
        .reset_index(drop=True)
    )

    return selected


def replace_infinities(series):
    """Infinities are not representable in JSON/Postgres numerics."""
    return series.replace([np.inf, -np.inf], np.nan)
