"""Shared helpers for the Silver -> Gold transformations.

Pure functions only: DataFrames in, DataFrames out. No EIA calls, no Supabase.
"""

import pandas as pd

DAILY_KEY = ["date", "respondent"]

HOURLY_KEY = ["period", "respondent"]

RESPONDENT_KEY = ["respondent"]


def normalize_silver(df, required_columns):
    """Standardize `period` and confirm the Silver contract is present."""
    df = df.copy()

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        # An empty domain contributes nothing to a join; only a frame that
        # actually carries rows has to honour the full Silver contract.
        if not df.empty:
            raise ValueError(
                f"Silver frame is missing required column(s): {missing}. "
                f"Got: {sorted(df.columns)}"
            )

        for column in missing:
            df[column] = pd.Series(dtype="object")

    if "respondent_name" not in df.columns:
        df["respondent_name"] = pd.NA

    df["period"] = pd.to_datetime(df["period"], utc=True, errors="coerce")

    return df


def add_calendar_date(df):
    """Calendar date (UTC) derived from `period`."""
    df = df.copy()
    df["date"] = df["period"].dt.date

    return df


def respondent_names(df, key):
    """First non-null respondent name per group."""
    names = (
        df.loc[:, key + ["respondent_name"]]
        .dropna(subset=["respondent_name"])
        .drop_duplicates(subset=key, keep="first")
    )

    return names


def attach_respondent_names(result, source, key):
    """Merge respondent names onto an aggregated frame."""
    return result.merge(respondent_names(source, key), on=key, how="left")
