import pandas as pd
import pytest

from extract.window import (
    LOOKBACK_HOURS,
    MAX_CATCHUP_HOURS,
    calculate_ingestion_end,
    calculate_ingestion_start,
    format_period,
)


def test_default_lookback_is_48_hours():
    assert LOOKBACK_HOURS == 48
    assert MAX_CATCHUP_HOURS == 24 * 7


def test_lookback_subtracts_48_hours():
    assert (
        calculate_ingestion_start("2026-08-29T12:00:00Z")
        == "2026-08-27T12"
    )


def test_lookback_handles_offset_timestamps_from_supabase():
    assert (
        calculate_ingestion_start("2026-08-29T12:00:00+00:00")
        == "2026-08-27T12"
    )


def test_lookback_crosses_month_boundaries():
    assert (
        calculate_ingestion_start("2026-09-01T01:00:00Z")
        == "2026-08-30T01"
    )


def test_custom_lookback_hours():
    assert (
        calculate_ingestion_start(
            "2026-08-29T12:00:00Z",
            lookback_hours=6,
        )
        == "2026-08-29T06"
    )


def test_no_checkpoint_returns_none():
    assert calculate_ingestion_start(None) is None


def test_unparseable_checkpoint_raises():
    with pytest.raises(ValueError, match="latest Bronze period"):
        calculate_ingestion_start("not-a-timestamp")


def test_format_period_matches_eia_hourly_format():
    stamp = pd.Timestamp("2026-08-29T12:34:56", tz="UTC")

    assert format_period(stamp) == "2026-08-29T12"


def test_recent_start_is_not_capped():
    recent = (
        pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=48)
    ).strftime("%Y-%m-%dT%H")

    assert calculate_ingestion_end(recent) is None


def test_stale_start_is_capped_to_the_catchup_window():
    assert (
        calculate_ingestion_end("2019-01-01T00", max_window_hours=24)
        == "2019-01-02T00"
    )


def test_no_start_means_no_cap():
    assert calculate_ingestion_end(None) is None


def test_unparseable_start_raises():
    with pytest.raises(ValueError, match="ingestion start"):
        calculate_ingestion_end("nope")
