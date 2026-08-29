import pandas as pd
import pytest

from transform.generation import (
    transform_generation,
    validate_generation,
)
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


def test_only_ng_records_survive():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 1000),
            raw_row("2024-01-01T00", "CAL", "DF", 900),
            raw_row("2024-01-01T00", "CAL", "NG", 5000),
            raw_row("2024-01-01T00", "CAL", "TI", -50),
        ]
    )

    out = transform_generation(raw)

    assert len(out) == 1
    assert out.loc[0, "net_generation_mwh"] == 5000


def test_output_columns_match_silver_contract():
    raw = pd.DataFrame([raw_row("2024-01-01T00", "CAL", "NG", 5000)])

    out = transform_generation(raw)

    assert list(out.columns) == [
        "period",
        "respondent",
        "respondent_name",
        "net_generation_mwh",
    ]
    assert out.loc[0, "respondent_name"] == "CAL Region"


def test_grain_is_unique_per_period_and_respondent():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "NG", 5000),
            raw_row("2024-01-01T01", "CAL", "NG", 5100),
            raw_row("2024-01-01T00", "NY", "NG", 2000),
        ]
    )

    out = validate_generation(transform_generation(raw))

    assert len(out) == 3
    assert not out.duplicated(subset=["period", "respondent"]).any()


def test_duplicate_grain_is_caught():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "NG", 5000),
            raw_row("2024-01-01T00", "CAL", "NG", 5001),
        ]
    )

    with pytest.raises(DataQualityError, match="grain"):
        validate_generation(transform_generation(raw))


def test_null_measurement_is_preserved_not_invented():
    raw = pd.DataFrame([raw_row("2024-01-01T00", "CAL", "NG", None)])

    out = validate_generation(transform_generation(raw))

    assert pd.isna(out.loc[0, "net_generation_mwh"])


def test_negative_generation_is_not_rejected():
    raw = pd.DataFrame([raw_row("2024-01-01T00", "CAL", "NG", -25)])

    out = validate_generation(transform_generation(raw))

    assert out.loc[0, "net_generation_mwh"] == -25
