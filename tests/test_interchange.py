import pandas as pd
import pytest

from transform.interchange import (
    transform_interchange,
    validate_interchange,
)
from transform.validation import SilverValidationError


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


def test_only_ti_records_survive():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "D", 1000),
            raw_row("2024-01-01T00", "CAL", "NG", 5000),
            raw_row("2024-01-01T00", "CAL", "TI", -50),
        ]
    )

    out = transform_interchange(raw)

    assert len(out) == 1
    assert out.loc[0, "total_interchange_mwh"] == -50


def test_output_columns_match_silver_contract():
    raw = pd.DataFrame([raw_row("2024-01-01T00", "CAL", "TI", 42)])

    out = transform_interchange(raw)

    assert list(out.columns) == [
        "period",
        "respondent",
        "respondent_name",
        "total_interchange_mwh",
    ]


def test_negative_interchange_is_preserved():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "TI", -120),
            raw_row("2024-01-01T01", "CAL", "TI", 120),
        ]
    )

    out = validate_interchange(transform_interchange(raw))

    assert out["total_interchange_mwh"].tolist() == [-120, 120]


def test_grain_is_unique_per_period_and_respondent():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "TI", -50),
            raw_row("2024-01-01T00", "NY", "TI", 30),
        ]
    )

    out = validate_interchange(transform_interchange(raw))

    assert not out.duplicated(subset=["period", "respondent"]).any()


def test_duplicate_grain_is_caught():
    raw = pd.DataFrame(
        [
            raw_row("2024-01-01T00", "CAL", "TI", -50),
            raw_row("2024-01-01T00", "CAL", "TI", -51),
        ]
    )

    with pytest.raises(SilverValidationError, match="grain"):
        validate_interchange(transform_interchange(raw))


def test_null_measurement_is_preserved_not_invented():
    raw = pd.DataFrame([raw_row("2024-01-01T00", "CAL", "TI", None)])

    out = validate_interchange(transform_interchange(raw))

    assert pd.isna(out.loc[0, "total_interchange_mwh"])
