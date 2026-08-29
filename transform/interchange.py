"""Silver interchange transformation: EIA `TI` -> one row per hour/region."""

import pandas as pd

from transform.common import (
    BUSINESS_KEY,
    normalize_raw,
    select_metric,
)
from transform.validation import (
    validate_business_key,
    validate_columns,
)

TABLE = "silver_interchange"

METRIC = "TI"

INTERCHANGE_COLUMNS = [
    "period",
    "respondent",
    "respondent_name",
    "total_interchange_mwh",
]


def transform_interchange(df):
    """Keep total interchange only. Pure function: DataFrame -> DataFrame."""
    df = normalize_raw(df)

    interchange = select_metric(df, METRIC, "total_interchange_mwh")

    if interchange.empty:
        return pd.DataFrame(columns=INTERCHANGE_COLUMNS)

    return (
        interchange.loc[:, INTERCHANGE_COLUMNS]
        .sort_values(BUSINESS_KEY)
        .reset_index(drop=True)
    )


def validate_interchange(df):
    """Structural checks for `silver_interchange`.

    Interchange is signed by design (imports vs. exports), so the sign of the
    EIA value is preserved and never validated against.
    """
    validate_columns(df, TABLE, INTERCHANGE_COLUMNS)
    validate_business_key(df, TABLE)

    return df
