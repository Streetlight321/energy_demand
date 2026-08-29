"""Lightweight data-quality checks for Silver DataFrames.

Structural violations raise `SilverValidationError` so the pipeline fails
loudly instead of writing bad rows into Supabase.
"""

import pandas as pd

from transform.common import BUSINESS_KEY


class SilverValidationError(ValueError):
    """Raised when a Silver DataFrame violates a structural expectation."""


def validate_business_key(df, table):
    """`period` / `respondent` must be present, non-null and unique."""
    missing = [
        column
        for column in BUSINESS_KEY
        if column not in df.columns
    ]

    if missing:
        raise SilverValidationError(
            f"{table}: missing business key column(s) {missing}"
        )

    for column in BUSINESS_KEY:
        null_count = int(df[column].isna().sum())

        if null_count:
            raise SilverValidationError(
                f"{table}: {null_count} row(s) have a null '{column}'"
            )

    duplicated = df.duplicated(subset=BUSINESS_KEY, keep=False)

    if bool(duplicated.any()):
        offenders = (
            df.loc[duplicated, BUSINESS_KEY]
            .drop_duplicates()
            .head(5)
            .to_dict(orient="records")
        )

        raise SilverValidationError(
            f"{table}: {int(duplicated.sum())} row(s) break the "
            f"(period, respondent) grain. Examples: {offenders}"
        )


def validate_columns(df, table, expected_columns):
    """The frame must expose exactly the agreed Silver contract."""
    missing = [
        column
        for column in expected_columns
        if column not in df.columns
    ]

    if missing:
        raise SilverValidationError(
            f"{table}: missing expected column(s) {missing}"
        )

    unexpected = [
        column
        for column in df.columns
        if column not in expected_columns
    ]

    if unexpected:
        raise SilverValidationError(
            f"{table}: unexpected column(s) {unexpected}"
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
        raise SilverValidationError(
            f"{table}: missing column '{column}'"
        )

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
