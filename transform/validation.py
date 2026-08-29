"""Lightweight data-quality checks for Silver and Gold DataFrames.

Structural violations raise `DataQualityError` so the pipeline fails loudly
instead of writing bad rows into Supabase. Value anomalies that the upstream
source genuinely produces are warned about and loaded as reported.
"""

import pandas as pd

from transform.common import BUSINESS_KEY


class DataQualityError(ValueError):
    """Raised when a DataFrame violates a structural expectation."""


def validate_business_key(df, table, key=None):
    """Business key columns must be present, non-null and unique."""
    key = list(key or BUSINESS_KEY)

    missing = [column for column in key if column not in df.columns]

    if missing:
        raise DataQualityError(
            f"{table}: missing business key column(s) {missing}"
        )

    for column in key:
        null_count = int(df[column].isna().sum())

        if null_count:
            raise DataQualityError(
                f"{table}: {null_count} row(s) have a null '{column}'"
            )

    duplicated = df.duplicated(subset=key, keep=False)

    if bool(duplicated.any()):
        offenders = (
            df.loc[duplicated, key]
            .drop_duplicates()
            .head(5)
            .to_dict(orient="records")
        )

        raise DataQualityError(
            f"{table}: {int(duplicated.sum())} row(s) break the "
            f"({', '.join(key)}) grain. Examples: {offenders}"
        )


def validate_columns(df, table, expected_columns):
    """The frame must expose exactly the agreed table contract."""
    missing = [
        column
        for column in expected_columns
        if column not in df.columns
    ]

    if missing:
        raise DataQualityError(
            f"{table}: missing expected column(s) {missing}"
        )

    unexpected = [
        column
        for column in df.columns
        if column not in expected_columns
    ]

    if unexpected:
        raise DataQualityError(
            f"{table}: unexpected column(s) {unexpected}"
        )


def validate_non_negative(df, table, columns):
    """Metrics that cannot be negative by construction (MAE, RMSE, counts).

    Nulls are legitimate analytical values and are ignored.
    """
    for column in columns:
        if column not in df.columns:
            raise DataQualityError(f"{table}: missing column '{column}'")

        values = pd.to_numeric(df[column], errors="coerce")
        negative = values.notna() & (values < 0)

        if bool(negative.any()):
            raise DataQualityError(
                f"{table}: {int(negative.sum())} row(s) have a negative "
                f"'{column}' (min {values[negative].min()})"
            )


def validate_ordered(df, table, upper, lower):
    """`upper` must be >= `lower` wherever both values exist."""
    for column in (upper, lower):
        if column not in df.columns:
            raise DataQualityError(f"{table}: missing column '{column}'")

    high = pd.to_numeric(df[upper], errors="coerce")
    low = pd.to_numeric(df[lower], errors="coerce")
    broken = high.notna() & low.notna() & (high < low)

    if bool(broken.any()):
        raise DataQualityError(
            f"{table}: {int(broken.sum())} row(s) have '{upper}' below "
            f"'{lower}'"
        )


def warn_negative_values(df, table, column):
    """Report negative values without failing the run.

    Negative hourly demand is rare but real in the EIA feed (small balancing
    authorities occasionally report it). It is a data-quality signal, not a
    structural violation, so the rows are loaded as reported and surfaced in
    the log instead of aborting a pipeline that has already written Bronze.

    Returns the number of offending rows.
    """
    if column not in df.columns:
        raise DataQualityError(f"{table}: missing column '{column}'")

    values = pd.to_numeric(df[column], errors="coerce")
    negative = values.notna() & (values < 0)
    count = int(negative.sum())

    if count:
        examples = (
            df.loc[negative, BUSINESS_KEY + [column]]
            .head(3)
            .to_dict(orient="records")
        )

        print(
            f"WARNING {table}: {count} row(s) have a negative '{column}' "
            f"(min {values[negative].min()}); loading as reported by the "
            f"EIA. Examples: {examples}"
        )

    return count
