import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill  # noqa: E402


def test_windows_cover_the_range_without_gaps():
    windows = list(
        backfill.iter_windows("2024-01-01T00", "2024-01-10T23", chunk_days=5)
    )

    assert windows == [
        ("2024-01-01T00", "2024-01-06T00"),
        ("2024-01-06T01", "2024-01-10T23"),
    ]


def test_single_window_when_range_fits_in_one_chunk():
    windows = list(
        backfill.iter_windows("2024-01-01T00", "2024-01-02T00", chunk_days=30)
    )

    assert windows == [("2024-01-01T00", "2024-01-02T00")]


def test_inverted_range_raises():
    with pytest.raises(ValueError, match="after end"):
        list(
            backfill.iter_windows(
                "2024-02-01T00", "2024-01-01T00", chunk_days=30
            )
        )


def test_backfill_walks_every_chunk(monkeypatch):
    seen = []

    def fake_ingest(start=None, end=None):
        seen.append((start, end))
        return {"rows_extracted": 10}

    monkeypatch.setattr(backfill, "ingest_window", fake_ingest)

    total = backfill.run_backfill(
        "2024-01-01T00", "2024-01-10T23", chunk_days=5
    )

    assert total == 20
    assert seen == [
        ("2024-01-01T00", "2024-01-06T00"),
        ("2024-01-06T01", "2024-01-10T23"),
    ]


def test_default_start_is_explicit_and_historical():
    assert backfill.DEFAULT_START == "2019-01-01T00"
    assert backfill.parse_args([]).start == backfill.DEFAULT_START
    assert backfill.parse_args(["--start", "2020-01-01T00"]).start == (
        "2020-01-01T00"
    )
