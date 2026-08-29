import pandas as pd
import pytest

from transform.gold.grid_balance import (
    transform_gold_grid_balance_hourly,
    validate_gold_grid_balance_hourly,
)
from transform.validation import DataQualityError


def demand_frame(rows):
    return pd.DataFrame(
        [
            {
                "period": period,
                "respondent": respondent,
                "respondent_name": f"{respondent} Region",
                "demand_mwh": value,
                "forecast_demand_mwh": None,
                "forecast_error_mwh": None,
                "forecast_error_pct": None,
            }
            for period, respondent, value in rows
        ]
    )


def domain_frame(rows, column):
    return pd.DataFrame(
        [
            {
                "period": period,
                "respondent": respondent,
                "respondent_name": f"{respondent} Region",
                column: value,
            }
            for period, respondent, value in rows
        ]
    )


def test_joins_the_three_domains_on_period_and_respondent():
    demand = demand_frame([("2026-01-01T00", "CAL", 100.0)])
    generation = domain_frame(
        [("2026-01-01T00", "CAL", 150.0)], "net_generation_mwh"
    )
    interchange = domain_frame(
        [("2026-01-01T00", "CAL", -20.0)], "total_interchange_mwh"
    )

    out = validate_gold_grid_balance_hourly(
        transform_gold_grid_balance_hourly(demand, generation, interchange)
    )

    assert len(out) == 1
    row = out.loc[0]
    assert row["demand_mwh"] == 100
    assert row["net_generation_mwh"] == 150
    assert row["total_interchange_mwh"] == -20
    assert row["generation_minus_demand_mwh"] == 50
    assert row["respondent_name"] == "CAL Region"


def test_generation_minus_demand_can_be_negative():
    demand = demand_frame([("2026-01-01T00", "CAL", 500.0)])
    generation = domain_frame(
        [("2026-01-01T00", "CAL", 300.0)], "net_generation_mwh"
    )
    interchange = domain_frame([], "total_interchange_mwh")

    out = transform_gold_grid_balance_hourly(demand, generation, interchange)

    assert out.loc[0, "generation_minus_demand_mwh"] == -200


def test_missing_interchange_stays_null_and_is_not_zero_filled():
    demand = demand_frame([("2026-01-01T00", "CAL", 100.0)])
    generation = domain_frame(
        [("2026-01-01T00", "CAL", 150.0)], "net_generation_mwh"
    )
    interchange = domain_frame([], "total_interchange_mwh")

    out = transform_gold_grid_balance_hourly(demand, generation, interchange)

    assert pd.isna(out.loc[0, "total_interchange_mwh"])
    assert out.loc[0, "generation_minus_demand_mwh"] == 50


def test_missing_generation_leaves_the_difference_null():
    demand = demand_frame([("2026-01-01T00", "CAL", 100.0)])
    generation = domain_frame([], "net_generation_mwh")
    interchange = domain_frame(
        [("2026-01-01T00", "CAL", -20.0)], "total_interchange_mwh"
    )

    out = transform_gold_grid_balance_hourly(demand, generation, interchange)

    assert pd.isna(out.loc[0, "net_generation_mwh"])
    assert pd.isna(out.loc[0, "generation_minus_demand_mwh"])
    assert out.loc[0, "demand_mwh"] == 100


def test_hours_present_only_in_generation_are_kept():
    demand = demand_frame([("2026-01-01T00", "CAL", 100.0)])
    generation = domain_frame(
        [("2026-01-01T01", "NY", 75.0)], "net_generation_mwh"
    )
    interchange = domain_frame([], "total_interchange_mwh")

    out = validate_gold_grid_balance_hourly(
        transform_gold_grid_balance_hourly(demand, generation, interchange)
    )

    assert len(out) == 2
    ny = out[out["respondent"] == "NY"].iloc[0]
    assert pd.isna(ny["demand_mwh"])
    assert ny["net_generation_mwh"] == 75
    assert ny["respondent_name"] == "NY Region"


def test_grain_is_unique_across_many_hours_and_regions():
    demand = demand_frame(
        [
            ("2026-01-01T00", "CAL", 100.0),
            ("2026-01-01T01", "CAL", 110.0),
            ("2026-01-01T00", "NY", 50.0),
        ]
    )
    generation = domain_frame(
        [
            ("2026-01-01T00", "CAL", 120.0),
            ("2026-01-01T01", "CAL", 130.0),
        ],
        "net_generation_mwh",
    )
    interchange = domain_frame(
        [("2026-01-01T00", "NY", 5.0)], "total_interchange_mwh"
    )

    out = validate_gold_grid_balance_hourly(
        transform_gold_grid_balance_hourly(demand, generation, interchange)
    )

    assert len(out) == 3
    assert not out.duplicated(subset=["period", "respondent"]).any()


def test_demand_side_name_wins_and_conflicts_are_warned(capsys):
    demand = demand_frame([("2026-01-01T00", "CAL", 100.0)])
    generation = pd.DataFrame(
        [
            {
                "period": "2026-01-01T00",
                "respondent": "CAL",
                "respondent_name": "A Different Name",
                "net_generation_mwh": 150.0,
            }
        ]
    )
    interchange = domain_frame([], "total_interchange_mwh")

    out = transform_gold_grid_balance_hourly(demand, generation, interchange)

    assert out.loc[0, "respondent_name"] == "CAL Region"
    assert "WARNING" in capsys.readouterr().out


def test_duplicate_input_grain_is_caught_by_validation():
    demand = demand_frame(
        [("2026-01-01T00", "CAL", 100.0), ("2026-01-01T00", "CAL", 105.0)]
    )
    generation = domain_frame([], "net_generation_mwh")
    interchange = domain_frame([], "total_interchange_mwh")

    with pytest.raises(DataQualityError, match="grain"):
        validate_gold_grid_balance_hourly(
            transform_gold_grid_balance_hourly(
                demand, generation, interchange
            )
        )
