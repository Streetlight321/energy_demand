import math

import pandas as pd
import pytest

from transform.gold.forecast_performance import (
    transform_gold_forecast_performance_daily,
    validate_gold_forecast_performance_daily,
)
from transform.validation import DataQualityError


def silver_row(period, respondent, demand, forecast):
    error = (
        None
        if demand is None or forecast is None
        else demand - forecast
    )

    return {
        "period": period,
        "respondent": respondent,
        "respondent_name": f"{respondent} Region",
        "demand_mwh": demand,
        "forecast_demand_mwh": forecast,
        "forecast_error_mwh": error,
        "forecast_error_pct": None,
    }


def known_day():
    """Errors of +100, -200, +300 against actuals of 1000, 800, 1500."""
    return pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 1000, 900),
            silver_row("2026-01-01T01", "CAL", 800, 1000),
            silver_row("2026-01-01T02", "CAL", 1500, 1200),
        ]
    )


def test_mae_is_the_mean_absolute_error():
    out = transform_gold_forecast_performance_daily(known_day())

    # (100 + 200 + 300) / 3
    assert out.loc[0, "mae_mwh"] == pytest.approx(200.0)


def test_rmse_is_the_root_mean_squared_error():
    out = transform_gold_forecast_performance_daily(known_day())

    expected = math.sqrt((100**2 + 200**2 + 300**2) / 3)
    assert out.loc[0, "rmse_mwh"] == pytest.approx(expected)


def test_mape_is_the_mean_absolute_percentage_error():
    out = transform_gold_forecast_performance_daily(known_day())

    expected = (
        (100 / 1000 + 200 / 800 + 300 / 1500) / 3
    ) * 100
    assert out.loc[0, "mape_pct"] == pytest.approx(expected)


def test_forecast_bias_keeps_its_sign():
    out = transform_gold_forecast_performance_daily(known_day())

    # (+100 - 200 + 300) / 3: net positive, actual exceeded forecast.
    assert out.loc[0, "forecast_bias_mwh"] == pytest.approx(200 / 3)


def test_bias_is_negative_when_demand_came_in_below_forecast():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 800, 1000),
            silver_row("2026-01-01T01", "CAL", 900, 1000),
        ]
    )

    out = transform_gold_forecast_performance_daily(df)

    assert out.loc[0, "forecast_bias_mwh"] == pytest.approx(-150.0)


def test_max_absolute_error():
    out = transform_gold_forecast_performance_daily(known_day())

    assert out.loc[0, "max_abs_error_mwh"] == 300


def test_observation_count_only_counts_usable_pairs():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 1000, 900),
            silver_row("2026-01-01T01", "CAL", None, 900),
            silver_row("2026-01-01T02", "CAL", 1000, None),
        ]
    )

    out = validate_gold_forecast_performance_daily(
        transform_gold_forecast_performance_daily(df)
    )

    assert out.loc[0, "observation_count"] == 1
    assert out.loc[0, "mae_mwh"] == 100


def test_zero_demand_rows_are_excluded_from_mape_but_not_mae():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 1000, 900),
            silver_row("2026-01-01T01", "CAL", 0, 100),
        ]
    )

    out = validate_gold_forecast_performance_daily(
        transform_gold_forecast_performance_daily(df)
    )

    # MAPE from the single usable hour only: 100/1000.
    assert out.loc[0, "mape_pct"] == pytest.approx(10.0)
    assert not math.isinf(out.loc[0, "mape_pct"])
    # The zero-demand hour still contributes to the absolute metrics.
    assert out.loc[0, "mae_mwh"] == pytest.approx(100.0)
    assert out.loc[0, "observation_count"] == 2


def test_day_without_any_usable_pair_is_null_not_zero():
    df = pd.DataFrame([silver_row("2026-01-01T00", "CAL", None, None)])

    out = validate_gold_forecast_performance_daily(
        transform_gold_forecast_performance_daily(df)
    )

    assert out.loc[0, "observation_count"] == 0
    assert pd.isna(out.loc[0, "mae_mwh"])
    assert pd.isna(out.loc[0, "mape_pct"])


def test_metrics_are_recomputed_not_averaged_from_silver_percentages():
    """A poisoned Silver percentage column must not reach Gold."""
    df = known_day()
    df["forecast_error_pct"] = 9999.0

    out = transform_gold_forecast_performance_daily(df)

    assert out.loc[0, "mape_pct"] < 100


def test_groups_by_date_and_respondent():
    df = pd.DataFrame(
        [
            silver_row("2026-01-01T00", "CAL", 1000, 900),
            silver_row("2026-01-02T00", "CAL", 1000, 900),
            silver_row("2026-01-01T00", "NY", 500, 400),
        ]
    )

    out = validate_gold_forecast_performance_daily(
        transform_gold_forecast_performance_daily(df)
    )

    assert len(out) == 3


def test_negative_metric_is_rejected_by_validation():
    broken = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-01-01").date(),
                "respondent": "CAL",
                "respondent_name": "CAL Region",
                "mae_mwh": -1.0,
                "rmse_mwh": 1.0,
                "mape_pct": 1.0,
                "forecast_bias_mwh": -5.0,
                "max_abs_error_mwh": 1.0,
                "observation_count": 1,
            }
        ]
    )

    with pytest.raises(DataQualityError, match="mae_mwh"):
        validate_gold_forecast_performance_daily(broken)
