"""gold_grid_balance_hourly: demand, generation and interchange side by side."""

import pandas as pd

from transform.gold.common import HOURLY_KEY, normalize_silver
from transform.validation import validate_business_key, validate_columns

TABLE = "gold_grid_balance_hourly"

GOLD_COLUMNS = [
    "period",
    "respondent",
    "respondent_name",
    "demand_mwh",
    "net_generation_mwh",
    "total_interchange_mwh",
    "generation_minus_demand_mwh",
]


def transform_gold_grid_balance_hourly(
    demand_df,
    generation_df,
    interchange_df,
):
    """Outer-join the three Silver domains on (period, respondent).

    An outer join keeps hours where only some domains reported. Missing
    measurements stay null: filling them with zero would fabricate a balance
    that the EIA never published.

    `generation_minus_demand_mwh` is deliberately named after its arithmetic.
    It is not labelled surplus/deficit or import/export, because interchange
    accounting and behind-the-meter generation make that reading unsafe
    without verified EIA semantics.
    """
    demand = normalize_silver(
        demand_df, ["period", "respondent", "demand_mwh"]
    ).loc[:, ["period", "respondent", "respondent_name", "demand_mwh"]]

    generation = normalize_silver(
        generation_df, ["period", "respondent", "net_generation_mwh"]
    ).loc[
        :, ["period", "respondent", "respondent_name", "net_generation_mwh"]
    ]

    interchange = normalize_silver(
        interchange_df, ["period", "respondent", "total_interchange_mwh"]
    ).loc[
        :,
        ["period", "respondent", "respondent_name", "total_interchange_mwh"],
    ]

    balance = demand.merge(
        generation,
        on=HOURLY_KEY,
        how="outer",
        suffixes=("", "_generation"),
    ).merge(
        interchange,
        on=HOURLY_KEY,
        how="outer",
        suffixes=("", "_interchange"),
    )

    _warn_name_conflicts(balance)

    # The demand-side name wins; the others only fill gaps.
    balance["respondent_name"] = (
        balance["respondent_name"]
        .fillna(balance.get("respondent_name_generation"))
        .fillna(balance.get("respondent_name_interchange"))
    )

    balance["generation_minus_demand_mwh"] = (
        balance["net_generation_mwh"] - balance["demand_mwh"]
    )

    if balance.empty:
        return pd.DataFrame(columns=GOLD_COLUMNS)

    return (
        balance.loc[:, GOLD_COLUMNS]
        .sort_values(HOURLY_KEY)
        .reset_index(drop=True)
    )


def _warn_name_conflicts(balance):
    """Surface respondents whose name differs between Silver domains."""
    for side in ("generation", "interchange"):
        column = f"respondent_name_{side}"

        if column not in balance.columns:
            continue

        conflicting = balance[
            balance["respondent_name"].notna()
            & balance[column].notna()
            & (balance["respondent_name"] != balance[column])
        ]

        if not conflicting.empty:
            examples = (
                conflicting.loc[
                    :, ["respondent", "respondent_name", column]
                ]
                .drop_duplicates()
                .head(3)
                .to_dict(orient="records")
            )

            print(
                f"WARNING {TABLE}: respondent_name differs between demand "
                f"and {side} for {conflicting['respondent'].nunique()} "
                f"respondent(s); keeping the demand-side name. "
                f"Examples: {examples}"
            )


def validate_gold_grid_balance_hourly(df):
    validate_columns(df, TABLE, GOLD_COLUMNS)
    validate_business_key(df, TABLE, key=HOURLY_KEY)

    return df
