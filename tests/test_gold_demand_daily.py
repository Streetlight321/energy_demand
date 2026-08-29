import pandas as pd
import pytest

from transform.gold.demand_daily import (
    transform_gold_demand_daily,
    validate_gold_demand_daily,
)
from transform.validation import DataQualityError


def silver_row(period, respondent, demand, forecast=None, name=None):
    return {
        "period": period,
        "respondent": respondent,
        "respondent_name": name or f"{respondent} Region",
        "demand_mwh": demand,
        "forecast_demand_mwh": forecast,
        "forecast_error_mwh": None,
        "forecast_error_pct": None,
    }


def test_daily_mean_peak_min_and_count():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 100),
            silver_row("2026-01-01T01", "CAL", 200),
            silver_row("2026-01-01T02", "CAL", 300),
        ]
    )

    out = validate_gold_demand_daily(transform_gold_demand_daily(df))

    assert len(out) == 1
    row = out.loc[0]
    assert row["avg_demand_mwh"] == 200
    assert row["peak_demand_mwh"] == 300
    assert row["min_demand_mwh"] == 100
    assert row["observation_count"] == 3
    assert row["demand_stddev_mwh"] == pytest.approx(100.0)
    assert row["respondent_name"] == "CAL Region"


def test_groups_by_date_and_respondent():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 100),
            silver_row("2026-01-01T23", "CAL", 300),
            silver_row("2026-01-02T00", "CAL", 50),
            silver_row("2026-01-01T00", "NY", 10),
        ]
    )

    out = transform_gold_demand_daily(df)

    assert len(out) == 3
    assert list(out.columns) == [
        "date",
        "respondent",
        "respondent_name",
        "avg_demand_mwh",
        "peak_demand_mwh",
        "min_demand_mwh",
        "demand_stddev_mwh",
        "observation_count",
    ]

    cal_day_one = out[
        (out["respondent"] == "CAL")
        & (out["date"].astype(str) == "2026-01-01")
    ].iloc[0]

    assert cal_day_one["avg_demand_mwh"] == 200
    assert cal_day_one["observation_count"] == 2


def test_dates_are_derived_in_utc_from_period():
    df = pd.DataFrame([silver_row("2026-01-01T23:00:00Z", "CAL", 100)])

    out = transform_gold_demand_daily(df)

    assert str(out.loc[0, "date"]) == "2026-01-01"


def test_null_demand_is_excluded_from_the_observation_count():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 100),
            silver_row("2026-01-01T01", "CAL", None),
        ]
    )

    out = validate_gold_demand_daily(transform_gold_demand_daily(df))

    assert out.loc[0, "observation_count"] == 1
    assert out.loc[0, "avg_demand_mwh"] == 100


def test_day_with_only_null_demand_yields_null_metrics_not_zero():
    df = pd.DataFrame([silver_row("2026-01-01T00", "CAL", None, forecast=90)])

    out = validate_gold_demand_daily(transform_gold_demand_daily(df))

    assert out.loc[0, "observation_count"] == 0
    assert pd.isna(out.loc[0, "avg_demand_mwh"])
    assert pd.isna(out.loc[0, "peak_demand_mwh"])


def test_single_observation_gives_null_stddev():
    df = pd.DataFrame([silver_row("2026-01-01T00", "CAL", 100)])

    out = validate_gold_demand_daily(transform_gold_demand_daily(df))

    assert pd.isna(out.loc[0, "demand_stddev_mwh"])


def test_empty_input_returns_the_gold_contract():
    out = transform_gold_demand_daily(
        pd.DataFrame(
            columns=["period", "respondent", "respondent_name", "demand_mwh"]
        )
    )

    assert out.empty
    assert "avg_demand_mwh" in out.columns


def test_transformation_is_deterministic():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 100),
            silver_row("2026-01-01T01", "CAL", 200),
        ]
    )

    first = transform_gold_demand_daily(df)
    second = transform_gold_demand_daily(df)

    pd.testing.assert_frame_equal(first, second)


def test_validation_catches_duplicate_business_keys():
    duplicated = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-01-01").date(),
                "respondent": "CAL",
                "respondent_name": "CAL Region",
                "avg_demand_mwh": 100.0,
                "peak_demand_mwh": 100.0,
                "min_demand_mwh": 100.0,
                "demand_stddev_mwh": None,
                "observation_count": 1,
            }
        ]
        * 2
    )

    with pytest.raises(DataQualityError, match="grain"):
        validate_gold_demand_daily(duplicated)


def test_validation_catches_peak_below_minimum():
    broken = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-01-01").date(),
                "respondent": "CAL",
                "respondent_name": "CAL Region",
                "avg_demand_mwh": 100.0,
                "peak_demand_mwh": 10.0,
                "min_demand_mwh": 200.0,
                "demand_stddev_mwh": None,
                "observation_count": 2,
            }
        ]
    )

    with pytest.raises(DataQualityError, match="peak_demand_mwh"):
        validate_gold_demand_daily(broken)
