import pandas as pd
import pytest

import pipeline
from database import queries


def raw_frame():
    return pd.DataFrame(
        [
            {
                "period": "2026-08-29T00",
                "respondent": "CAL",
                "respondent-name": "California",
                "type": t,
                "type-name": t,
                "value": v,
                "value-units": "megawatthours",
            }
            for t, v in [("D", 1000), ("DF", 900), ("NG", 5000), ("TI", -50)]
        ]
    )


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, df, *args, **kwargs):
        self.calls.append(df)
        return len(df)


@pytest.fixture
def stubbed(monkeypatch):
    """Replace every I/O boundary; no EIA and no Supabase in these tests."""
    state = {"pull_kwargs": None, "loads": {}}

    def fake_pull(start=None, end=None):
        state["pull_kwargs"] = {"start": start, "end": end}
        return raw_frame()

    monkeypatch.setattr(pipeline, "pull_raw", fake_pull)

    for name in [
        "load_bronze",
        "load_silver_demand",
        "load_silver_generation",
        "load_silver_interchange",
        "load_gold_demand_daily",
        "load_gold_forecast_performance_daily",
        "load_gold_grid_balance_hourly",
        "load_gold_regional_summary",
    ]:
        recorder = Recorder()
        state["loads"][name] = recorder
        monkeypatch.setattr(pipeline, name, recorder)

    # Gold back-reads must never touch Supabase in unit tests.
    monkeypatch.setattr(
        pipeline,
        "fetch_silver_demand",
        lambda start, end=None: pd.DataFrame(),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_recent_forecast_performance",
        lambda start_date: pd.DataFrame(),
    )

    return state


def test_empty_bronze_fails_loudly_instead_of_backfilling(monkeypatch):
    monkeypatch.setattr(pipeline, "get_latest_bronze_period", lambda: None)

    def explode(*args, **kwargs):
        raise AssertionError("the scheduled run must not fetch history")

    monkeypatch.setattr(pipeline, "pull_raw", explode)

    with pytest.raises(RuntimeError, match="backfill"):
        pipeline.run_pipeline()


def test_incremental_run_starts_48_hours_before_the_checkpoint(
    monkeypatch, stubbed
):
    monkeypatch.setattr(
        pipeline,
        "get_latest_bronze_period",
        lambda: "2026-08-29T12:00:00+00:00",
    )

    counts = pipeline.run_pipeline()

    assert stubbed["pull_kwargs"] == {"start": "2026-08-27T12", "end": None}
    assert counts["rows_extracted"] == 4
    assert counts["demand_rows"] == 1
    assert counts["generation_rows"] == 1
    assert counts["interchange_rows"] == 1


def test_api_is_called_once_for_all_three_silver_domains(
    monkeypatch, stubbed
):
    calls = {"count": 0}
    original = pipeline.pull_raw

    def counting_pull(start=None, end=None):
        calls["count"] += 1
        return original(start=start, end=end)

    monkeypatch.setattr(pipeline, "pull_raw", counting_pull)
    monkeypatch.setattr(
        pipeline,
        "get_latest_bronze_period",
        lambda: "2026-08-29T12:00:00Z",
    )

    pipeline.run_pipeline()

    assert calls["count"] == 1

    for name in stubbed["loads"]:
        assert len(stubbed["loads"][name].calls) == 1


def test_empty_extraction_skips_all_loads(monkeypatch, stubbed):
    monkeypatch.setattr(
        pipeline,
        "pull_raw",
        lambda start=None, end=None: pd.DataFrame(),
    )

    counts = pipeline.ingest_window(start="2026-08-27T12")

    assert counts["rows_extracted"] == 0

    for recorder in stubbed["loads"].values():
        assert recorder.calls == []


class FakeExecute:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, data, log):
        self._data = data
        self._log = log

    def select(self, *columns):
        self._log["select"] = columns
        return self

    def order(self, column, desc=False):
        self._log["order"] = (column, desc)
        return self

    def limit(self, n):
        self._log["limit"] = n
        return self

    def execute(self):
        return FakeExecute(self._data)


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.log = {}

    def table(self, name):
        self.log["table"] = name
        return FakeTable(self.data, self.log)


def test_latest_bronze_period_reads_the_newest_row():
    client = FakeClient([{"period": "2026-08-29T12:00:00+00:00"}])

    period = queries.get_latest_bronze_period(client=client)

    assert period == "2026-08-29T12:00:00+00:00"
    assert client.log["table"] == "bronze_eia_region_data"
    assert client.log["order"] == ("period", True)
    assert client.log["limit"] == 1


def test_latest_bronze_period_is_none_when_bronze_is_empty():
    client = FakeClient([])

    assert queries.get_latest_bronze_period(client=client) is None


def test_stale_bronze_run_is_capped_instead_of_pulling_years(
    monkeypatch, stubbed
):
    monkeypatch.setattr(
        pipeline,
        "get_latest_bronze_period",
        lambda: "2019-01-01T17:00:00+00:00",
    )

    pipeline.run_pipeline(max_window_hours=24)

    assert stubbed["pull_kwargs"] == {
        "start": "2018-12-30T17",
        "end": "2018-12-31T17",
    }


def test_gold_runs_from_the_silver_frames_of_this_run(monkeypatch, stubbed):
    monkeypatch.setattr(
        pipeline,
        "get_latest_bronze_period",
        lambda: "2026-08-29T12:00:00Z",
    )

    counts = pipeline.run_pipeline()

    assert counts["gold_demand_daily_rows"] == 1
    assert counts["gold_forecast_performance_rows"] == 1
    assert counts["gold_grid_balance_rows"] == 1
    assert counts["gold_regional_summary_rows"] == 1


def test_partial_first_day_is_completed_from_silver(monkeypatch):
    """A window starting mid-day must not overwrite a full day's aggregate."""
    window = pd.DataFrame(
        [
            {
                "period": pd.Timestamp("2026-08-27T12", tz="UTC"),
                "respondent": "CAL",
                "respondent_name": "California",
                "demand_mwh": 100.0,
            }
        ]
    )

    requested = {}

    def fake_fetch(start, end=None):
        requested["start"] = start
        requested["end"] = end
        return pd.DataFrame(
            [
                {
                    "period": "2026-08-27T03:00:00+00:00",
                    "respondent": "CAL",
                    "respondent_name": "California",
                    "demand_mwh": 80.0,
                }
            ]
        )

    completed = pipeline.complete_partial_first_day(window, fetch=fake_fetch)

    # The head slice covers midnight up to the window start.
    assert requested["start"] == pd.Timestamp("2026-08-27T00", tz="UTC")
    assert requested["end"] == pd.Timestamp("2026-08-27T12", tz="UTC")
    assert len(completed) == 2
    assert sorted(completed["demand_mwh"]) == [80.0, 100.0]


def test_window_already_aligned_to_midnight_skips_the_back_read():
    window = pd.DataFrame(
        [
            {
                "period": pd.Timestamp("2026-08-27T00", tz="UTC"),
                "respondent": "CAL",
                "demand_mwh": 100.0,
            }
        ]
    )

    def explode(*args, **kwargs):
        raise AssertionError("no back-read needed for a full day")

    completed = pipeline.complete_partial_first_day(window, fetch=explode)

    assert len(completed) == 1


def test_recent_forecast_window_requests_seven_days():
    forecast_df = pd.DataFrame(
        [
            {"date": "2026-08-29", "respondent": "CAL"},
            {"date": "2026-08-28", "respondent": "CAL"},
        ]
    )

    requested = {}

    def fake_fetch(start_date):
        requested["start_date"] = start_date
        return pd.DataFrame()

    pipeline.recent_forecast_performance(forecast_df, fetch=fake_fetch)

    assert requested["start_date"] == pd.Timestamp("2026-08-23")
