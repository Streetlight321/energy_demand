"""Silver generation transformation: EIA `NG` -> one row per hour/region."""

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

TABLE = "silver_generation"

METRIC = "NG"

GENERATION_COLUMNS = [
    "period",
    "respondent",
    "respondent_name",
    "net_generation_mwh",
]


def transform_generation(df):
    """Keep net generation only. Pure function: DataFrame -> DataFrame."""
    df = normalize_raw(df)

    generation = select_metric(df, METRIC, "net_generation_mwh")

    if generation.empty:
        return pd.DataFrame(columns=GENERATION_COLUMNS)

    return (
        generation.loc[:, GENERATION_COLUMNS]
        .sort_values(BUSINESS_KEY)
        .reset_index(drop=True)
    )


def validate_generation(df):
    """Structural checks for `silver_generation`.

    Net generation is not sign-checked: the EIA value is preserved as-is.
    """
    validate_columns(df, TABLE, GENERATION_COLUMNS)
    validate_business_key(df, TABLE)

    return df
