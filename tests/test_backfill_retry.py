"""Window-level resilience in the historical backfill."""

import sys
from pathlib import Path

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill  # noqa: E402


def counts(rows=10):
    return {"rows_extracted": rows}


def test_window_succeeds_without_retrying():
    calls = []

    result = backfill.ingest_with_retry(
        "2024-01-01T00",
        "2024-01-31T23",
        sleep=lambda _: None,
        ingest=lambda start, end: calls.append((start, end)) or counts(),
    )

    assert result == counts()
    assert calls == [("2024-01-01T00", "2024-01-31T23")]


def test_transient_failure_replays_the_same_window(capsys):
    attempts = {"n": 0}
    delays = []

    def flaky(start, end):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ReadTimeout("The read operation timed out")
        return counts(42)

    result = backfill.ingest_with_retry(
        "2024-01-01T00", "2024-01-31T23", sleep=delays.append, ingest=flaky
    )

    assert result == counts(42)
    assert attempts["n"] == 2
    assert delays == [1.0]
    assert "replaying in 1s" in capsys.readouterr().out


def test_window_retries_are_bounded():
    attempts = {"n": 0}
    delays = []

    def always_fails(start, end):
        attempts["n"] += 1
        raise httpx.ReadTimeout("The read operation timed out")

    with pytest.raises(httpx.ReadTimeout):
        backfill.ingest_with_retry(
            "2024-01-01T00",
            "2024-01-31T23",
            attempts=3,
            sleep=delays.append,
            ingest=always_fails,
        )

    assert attempts["n"] == 3, "must not retry forever"
    assert delays == [1.0, 2.0]


def test_persistent_error_is_not_hidden():
    """A missing table must fail on the first window, not be replayed."""
    attempts = {"n": 0}

    def missing_table(start, end):
        attempts["n"] += 1
        raise APIError({"message": "no table", "code": "PGRST205"})

    with pytest.raises(APIError):
        backfill.ingest_with_retry(
            "2024-01-01T00", "2024-01-31T23",
            sleep=lambda _: None, ingest=missing_table,
        )

    assert attempts["n"] == 1


def test_backfill_continues_across_windows_after_a_transient_failure(monkeypatch):
    seen = []
    failed_once = {"done": False}

    def flaky(start=None, end=None):
        if start == "2024-01-31T01" and not failed_once["done"]:
            failed_once["done"] = True
            raise httpx.ConnectError("connection reset")
        seen.append((start, end))
        return counts(5)

    monkeypatch.setattr(backfill, "ingest_window", flaky)
    monkeypatch.setattr(backfill.time, "sleep", lambda _: None)

    total = backfill.run_backfill("2024-01-01T00", "2024-03-01T00", chunk_days=30)

    assert total == 10, "both windows ingested"
    assert len(seen) == 2
    assert seen[1][0] == "2024-01-31T01", "the failed window was replayed"


def test_failure_reports_where_to_resume(monkeypatch, capsys):
    def fails_on_second(start=None, end=None):
        if start == "2024-01-31T01":
            raise httpx.ReadTimeout("The read operation timed out")
        return counts(7)

    monkeypatch.setattr(backfill, "ingest_window", fails_on_second)
    monkeypatch.setattr(backfill.time, "sleep", lambda _: None)

    with pytest.raises(httpx.ReadTimeout):
        backfill.run_backfill(
            "2024-01-01T00", "2024-03-01T00", chunk_days=30, window_attempts=2
        )

    out = capsys.readouterr().out
    assert "--start 2024-01-31T01" in out, "must say where to pick up"
    assert "7 raw rows were ingested before it" in out
