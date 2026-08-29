import math

import pandas as pd
import pytest

from transform.demand import transform_demand, validate_demand
from transform.validation import DataQualityError


def raw_row(period, respondent, type_code, value):
    return {
        "period": period,
        "respondent": respondent,
        "respondent-name": f"{respondent} Region",
        "type": type_code,
        "type-name": type_code,
        "value": value,
        "value-units": "megawatthours",
    }


def test_d_and_df_pivot_into_one_row():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 1000),
            raw_row("2024-01-01T00", "CAL", "DF", 900),
            raw_row("2024-01-01T00", "CAL", "NG", 5000),
            raw_row("2024-01-01T00", "CAL", "TI", -50),
        ]
    )

    out = transform_demand(raw)

    assert len(out) == 1
    assert out.loc[0, "demand_mwh"] == 1000
    assert out.loc[0, "forecast_demand_mwh"] == 900
    assert out.loc[0, "respondent_name"] == "CAL Region"
    assert list(out.columns) == [
        "period",
        "respondent",
        "respondent_name",
        "demand_mwh",
        "forecast_demand_mwh",
        "forecast_error_mwh",
        "forecast_error_pct",
    ]


def test_forecast_error_is_signed_actual_minus_forecast():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 1000),
            raw_row("2024-01-01T00", "CAL", "DF", 900),
            raw_row("2024-01-01T01", "CAL", "D", 800),
            raw_row("2024-01-01T01", "CAL", "DF", 1000),
        ]
    )

    out = transform_demand(raw).set_index("period")

    # Positive: actual exceeded forecast.
    assert out.iloc[0]["forecast_error_mwh"] == 100
    # Negative: actual came in below forecast.
    assert out.iloc[1]["forecast_error_mwh"] == -200


def test_forecast_error_pct_is_relative_to_actual_demand():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 1000),
            raw_row("2024-01-01T00", "CAL", "DF", 900),
        ]
    )

    out = transform_demand(raw)

    assert out.loc[0, "forecast_error_pct"] == pytest.approx(10.0)


def test_zero_demand_does_not_produce_infinity():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 0),
            raw_row("2024-01-01T00", "CAL", "DF", 100),
        ]
    )

    out = transform_demand(raw)

    assert out.loc[0, "forecast_error_mwh"] == -100
    assert pd.isna(out.loc[0, "forecast_error_pct"])
    assert not math.isinf(float(out.loc[0, "forecast_error_pct"] or 0))


def test_missing_measurements_do_not_crash():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", None),
            raw_row("2024-01-01T00", "CAL", "DF", 900),
            raw_row("2024-01-01T01", "CAL", "D", 500),
        ]
    )

    out = transform_demand(raw)

    assert len(out) == 2
    assert pd.isna(out.loc[0, "demand_mwh"])
    assert pd.isna(out.loc[0, "forecast_error_mwh"])
    # No value was invented for the missing forecast.
    assert pd.isna(out.loc[1, "forecast_demand_mwh"])


def test_validate_demand_accepts_clean_frame():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 1000),
            raw_row("2024-01-01T00", "CAL", "DF", 900),
            raw_row("2024-01-01T00", "NY", "D", 700),
        ]
    )

    out = transform_demand(raw)

    assert validate_demand(out) is out


def test_validate_demand_catches_duplicate_business_keys():
    duplicated = pd.DataFrame(
        [
            {
                "period": pd.Timestamp("2024-01-01T00", tz="UTC"),
                "respondent": "CAL",
                "respondent_name": "CAL Region",
                "demand_mwh": 1000.0,
                "forecast_demand_mwh": 900.0,
                "forecast_error_mwh": 100.0,
                "forecast_error_pct": 10.0,
            },
        ]
        * 2
    )

    with pytest.raises(DataQualityError, match="grain"):
        validate_demand(duplicated)


def test_validate_demand_catches_null_business_key():
    frame = pd.DataFrame(
        [
            {
                "period": pd.Timestamp("2024-01-01T00", tz="UTC"),
                "respondent": None,
                "respondent_name": "CAL Region",
                "demand_mwh": 1000.0,
                "forecast_demand_mwh": 900.0,
                "forecast_error_mwh": 100.0,
                "forecast_error_pct": 10.0,
            }
        ]
    )

    with pytest.raises(DataQualityError, match="respondent"):
        validate_demand(frame)


def test_negative_demand_is_warned_not_rejected(capsys):
    """The EIA really does report negative demand for some small BAs."""
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "SEC", "D", -81),
            raw_row("2024-01-01T00", "SEC", "DF", 145),
        ]
    )

    out = validate_demand(transform_demand(raw))

    assert out.loc[0, "demand_mwh"] == -81
    assert "WARNING" in capsys.readouterr().out


def test_negative_demand_keeps_signed_error_but_nulls_the_percentage():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "SEC", "D", -81),
            raw_row("2024-01-01T00", "SEC", "DF", 145),
        ]
    )

    out = transform_demand(raw)

    assert out.loc[0, "forecast_error_mwh"] == -226
    # -226 / -81 would read as +279%, which is meaningless.
    assert pd.isna(out.loc[0, "forecast_error_pct"])
