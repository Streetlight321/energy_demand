import pandas as pd
import pytest

from transform.gold.regional_summary import (
    RECENT_DAYS,
    transform_gold_regional_summary,
    validate_gold_regional_summary,
)
from transform.validation import DataQualityError


def demand_frame(rows):
    return pd.DataFrame(
        [
            {
                "period": period,
                "respondent": respondent,
                "respondent_name": f"{respondent} Region",
                "demand_mwh": demand,
                "forecast_demand_mwh": forecast,
                "forecast_error_mwh": None,
                "forecast_error_pct": None,
            }
            for period, respondent, demand, forecast in rows
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


def performance_frame(rows):
    return pd.DataFrame(
        [
            {
                "date": date,
                "respondent": respondent,
                "respondent_name": f"{respondent} Region",
                "mape_pct": mape,
                "forecast_bias_mwh": bias,
                "observation_count": count,
            }
            for date, respondent, mape, bias, count in rows
        ]
    )


def test_one_row_per_respondent_with_the_latest_observation():
    demand = demand_frame(
        [
            ("2026-01-01T00", "CAL", 100.0, 90.0),
            ("2026-01-01T05", "CAL", 130.0, 120.0),
            ("2026-01-01T03", "NY", 50.0, 55.0),
        ]
    )
    generation = domain_frame(
        [("2026-01-01T05", "CAL", 200.0)], "net_generation_mwh"
    )
    interchange = domain_frame(
        [("2026-01-01T05", "CAL", -15.0)], "total_interchange_mwh"
    )

    out = validate_gold_regional_summary(
        transform_gold_regional_summary(demand, generation, interchange)
    )

    assert len(out) == 2
    assert out["respondent"].tolist() == ["CAL", "NY"]

    cal = out[out["respondent"] == "CAL"].iloc[0]
    assert str(cal["latest_period"]) == "2026-01-01 05:00:00+00:00"
    assert cal["latest_demand_mwh"] == 130
    assert cal["latest_forecast_demand_mwh"] == 120
    assert cal["latest_net_generation_mwh"] == 200
    assert cal["latest_total_interchange_mwh"] == -15


def test_metric_missing_at_the_latest_hour_stays_null():
    """No reaching back to an older hour to fill a gap."""
    demand = demand_frame(
        [
            ("2026-01-01T00", "CAL", 100.0, 90.0),
            ("2026-01-01T05", "CAL", 130.0, 120.0),
        ]
    )
    generation = domain_frame(
        [("2026-01-01T00", "CAL", 200.0)], "net_generation_mwh"
    )
    interchange = domain_frame([], "total_interchange_mwh")

    out = transform_gold_regional_summary(demand, generation, interchange)

    assert out.loc[0, "latest_demand_mwh"] == 130
    assert pd.isna(out.loc[0, "latest_net_generation_mwh"])


def test_recent_forecast_kpis_use_the_documented_window():
    assert RECENT_DAYS == 7

    demand = demand_frame([("2026-01-10T00", "CAL", 100.0, 90.0)])
    generation = domain_frame([], "net_generation_mwh")
    interchange = domain_frame([], "total_interchange_mwh")

    performance = performance_frame(
        [
            # Inside the 7-day window ending on the latest date, 2026-01-10.
            ("2026-01-10", "CAL", 5.0, 10.0, 24),
            ("2026-01-04", "CAL", 7.0, -10.0, 24),
            # Outside it: must not influence the KPIs.
            ("2026-01-01", "CAL", 90.0, 900.0, 24),
        ]
    )

    out = validate_gold_regional_summary(
        transform_gold_regional_summary(
            demand, generation, interchange, performance
        )
    )

    assert out.loc[0, "recent_forecast_mape_pct"] == pytest.approx(6.0)
    assert out.loc[0, "recent_forecast_bias_mwh"] == pytest.approx(0.0)


def test_recent_kpis_are_weighted_by_observation_count():
    demand = demand_frame([("2026-01-10T00", "CAL", 100.0, 90.0)])
    empty_generation = domain_frame([], "net_generation_mwh")
    empty_interchange = domain_frame([], "total_interchange_mwh")

    performance = performance_frame(
        [
            ("2026-01-10", "CAL", 10.0, 0.0, 1),
            ("2026-01-09", "CAL", 20.0, 0.0, 3),
        ]
    )

    out = transform_gold_regional_summary(
        demand, empty_generation, empty_interchange, performance
    )

    # (10*1 + 20*3) / 4, not the unweighted 15.
    assert out.loc[0, "recent_forecast_mape_pct"] == pytest.approx(17.5)


def test_days_without_usable_metrics_do_not_break_the_kpis():
    demand = demand_frame([("2026-01-10T00", "CAL", 100.0, 90.0)])
    performance = performance_frame(
        [
            ("2026-01-10", "CAL", None, None, 0),
            ("2026-01-09", "CAL", 8.0, 4.0, 24),
        ]
    )

    out = validate_gold_regional_summary(
        transform_gold_regional_summary(
            demand,
            domain_frame([], "net_generation_mwh"),
            domain_frame([], "total_interchange_mwh"),
            performance,
        )
    )

    assert out.loc[0, "recent_forecast_mape_pct"] == pytest.approx(8.0)


def test_summary_without_forecast_history_still_returns_latest_state():
    demand = demand_frame([("2026-01-10T00", "CAL", 100.0, 90.0)])

    out = validate_gold_regional_summary(
        transform_gold_regional_summary(
            demand,
            domain_frame([], "net_generation_mwh"),
            domain_frame([], "total_interchange_mwh"),
        )
    )

    assert out.loc[0, "latest_demand_mwh"] == 100
    assert pd.isna(out.loc[0, "recent_forecast_mape_pct"])
    assert pd.isna(out.loc[0, "recent_forecast_bias_mwh"])


def test_output_contract_and_grain():
    demand = demand_frame(
        [
            ("2026-01-10T00", "CAL", 100.0, 90.0),
            ("2026-01-10T01", "CAL", 110.0, 95.0),
        ]
    )

    out = validate_gold_regional_summary(
        transform_gold_regional_summary(
            demand,
            domain_frame([], "net_generation_mwh"),
            domain_frame([], "total_interchange_mwh"),
        )
    )

    assert list(out.columns) == [
        "respondent",
        "respondent_name",
        "latest_period",
        "latest_demand_mwh",
        "latest_forecast_demand_mwh",
        "latest_net_generation_mwh",
        "latest_total_interchange_mwh",
        "recent_forecast_mape_pct",
        "recent_forecast_bias_mwh",
    ]
    assert len(out) == 1
    assert not out.duplicated(subset=["respondent"]).any()


def test_duplicate_respondents_are_rejected():
    duplicated = pd.DataFrame(
        [
            {
                "respondent": "CAL",
                "respondent_name": "CAL Region",
                "latest_period": pd.Timestamp("2026-01-10T00", tz="UTC"),
                "latest_demand_mwh": 100.0,
                "latest_forecast_demand_mwh": 90.0,
                "latest_net_generation_mwh": None,
                "latest_total_interchange_mwh": None,
                "recent_forecast_mape_pct": None,
                "recent_forecast_bias_mwh": None,
            }
        ]
        * 2
    )

    with pytest.raises(DataQualityError, match="grain"):
        validate_gold_regional_summary(duplicated)
