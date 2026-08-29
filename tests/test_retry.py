import httpx
import pytest
from postgrest.exceptions import APIError

from database.retry import (
    DEFAULT_ATTEMPTS,
    backoff_delay,
    describe,
    is_transient,
    run_with_retry,
)


def api_error(code):
    return APIError({"message": "boom", "code": code, "hint": None, "details": None})


class Recorder:
    """Stand-in for time.sleep that records the delays instead of waiting."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def test_default_attempts_is_five():
    assert DEFAULT_ATTEMPTS == 5


def test_backoff_is_exponential_and_capped():
    delays = [backoff_delay(attempt) for attempt in range(1, 8)]

    assert delays[:4] == [1.0, 2.0, 4.0, 8.0]
    assert max(delays) == 30.0
    assert delays == sorted(delays)


@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("read timed out"),
    httpx.ConnectTimeout("connect timed out"),
    httpx.WriteTimeout("write timed out"),
    httpx.PoolTimeout("pool timed out"),
    httpx.ConnectError("connection refused"),
    httpx.RemoteProtocolError("server disconnected"),
])
def test_transport_failures_are_transient(error):
    assert is_transient(error)


@pytest.mark.parametrize("code", ["408", "429", "500", "502", "503", "504"])
def test_overload_statuses_are_transient(code):
    assert is_transient(api_error(code))


@pytest.mark.parametrize("error", [
    api_error("PGRST205"),          # table missing from the schema cache
    api_error("23505"),             # unique violation
    api_error("400"),               # bad payload
    ValueError("bad data"),
    httpx.UnsupportedProtocol("nope"),
])
def test_application_errors_are_not_transient(error):
    assert not is_transient(error)


def test_successful_call_runs_once():
    calls = []

    result = run_with_retry(
        lambda: calls.append(1) or "ok",
        description="table rows 1-250",
        sleep=Recorder(),
    )

    assert result == "ok"
    assert len(calls) == 1


def test_timeout_then_success(capsys):
    """The exact failure mode from the backfill: one stall, then it works."""
    attempts = {"n": 0}
    sleep = Recorder()

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ReadTimeout("The read operation timed out")
        return "written"

    result = run_with_retry(
        flaky, description="bronze_eia_region_data rows 1501-1750", sleep=sleep
    )

    assert result == "written"
    assert attempts["n"] == 2
    assert sleep.delays == [1.0]

    out = capsys.readouterr().out
    assert "bronze_eia_region_data rows 1501-1750" in out
    assert "ReadTimeout" in out
    assert "attempt 2/5" in out


def test_retries_exhaust_and_reraise(capsys):
    attempts = {"n": 0}
    sleep = Recorder()

    def always_times_out():
        attempts["n"] += 1
        raise httpx.ReadTimeout("The read operation timed out")

    with pytest.raises(httpx.ReadTimeout):
        run_with_retry(
            always_times_out,
            description="silver_demand rows 1-250",
            attempts=4,
            sleep=sleep,
        )

    assert attempts["n"] == 4
    assert sleep.delays == [1.0, 2.0, 4.0]
    assert "giving up after 4 attempts" in capsys.readouterr().out


def test_non_transient_error_is_raised_immediately():
    attempts = {"n": 0}
    sleep = Recorder()

    def missing_table():
        attempts["n"] += 1
        raise api_error("PGRST205")

    with pytest.raises(APIError):
        run_with_retry(missing_table, description="gold_demand_daily", sleep=sleep)

    assert attempts["n"] == 1, "a permanent error must not be retried"
    assert sleep.delays == []


def test_transient_api_error_is_retried():
    attempts = {"n": 0}

    def overloaded():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise api_error("503")
        return "ok"

    assert run_with_retry(overloaded, description="t", sleep=Recorder()) == "ok"
    assert attempts["n"] == 3


def test_describe_includes_type_and_message():
    assert "ReadTimeout" in describe(httpx.ReadTimeout("timed out"))
    assert "boom" in describe(api_error("503"))


def test_attempts_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        run_with_retry(lambda: None, description="t", attempts=0)
