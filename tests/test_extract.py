import pandas as pd
import pytest
import requests

from extract.pull_data import PAGE_SIZE, build_session, get_api_key, pull_raw


class FakeResponse:
    def __init__(self, rows, status_error=None):
        self.rows = rows
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return {"response": {"data": self.rows}}


class FakeSession:
    """Records every request and replays canned pages."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))

        page = self.pages.pop(0) if self.pages else []

        if isinstance(page, FakeResponse):
            return page

        return FakeResponse(page)

    def close(self):
        self.closed = True


def rows(count, offset=0):
    return [
        {
            "period": "2026-08-29T00",
            "respondent": f"R{offset + i}",
            "respondent-name": "Region",
            "type": "D",
            "type-name": "Demand",
            "value": 100,
            "value-units": "megawatthours",
        }
        for i in range(count)
    ]


def test_pagination_combines_pages_and_stops_on_short_page():
    session = FakeSession([rows(PAGE_SIZE), rows(382, offset=PAGE_SIZE)])

    df = pull_raw(session=session)

    assert len(df) == PAGE_SIZE + 382
    assert isinstance(df, pd.DataFrame)
    # Two requests only: the short second page ends pagination.
    assert len(session.calls) == 2


def test_offset_increments_by_page_size():
    session = FakeSession([rows(PAGE_SIZE), rows(PAGE_SIZE), rows(1)])

    pull_raw(session=session)

    assert [call["offset"] for call in session.calls] == [
        0,
        PAGE_SIZE,
        2 * PAGE_SIZE,
    ]
    assert {call["length"] for call in session.calls} == {PAGE_SIZE}


def test_empty_first_page_returns_empty_frame():
    session = FakeSession([[]])

    df = pull_raw(session=session)

    assert df.empty
    assert len(session.calls) == 1


def test_exactly_full_last_page_then_empty_page():
    session = FakeSession([rows(PAGE_SIZE), []])

    df = pull_raw(session=session)

    assert len(df) == PAGE_SIZE
    assert len(session.calls) == 2


def test_api_key_is_always_sent():
    """Regression: a missing api_key param made the EIA answer 403."""
    session = FakeSession([rows(1)])

    pull_raw(session=session)

    assert session.calls[0]["api_key"] == get_api_key()


def test_eia_query_parameters_are_preserved():
    session = FakeSession([rows(1)])

    pull_raw(session=session)

    params = session.calls[0]

    assert params["frequency"] == "hourly"
    assert params["data[0]"] == "value"
    assert params["sort[0][column]"] == "period"
    assert params["sort[0][direction]"] == "asc"


def test_start_and_end_are_omitted_when_none():
    session = FakeSession([rows(1)])

    pull_raw(session=session)

    assert "start" not in session.calls[0]
    assert "end" not in session.calls[0]


def test_start_and_end_are_forwarded_when_given():
    session = FakeSession([rows(1)])

    pull_raw(start="2026-08-27T12", end="2026-08-29T12", session=session)

    assert session.calls[0]["start"] == "2026-08-27T12"
    assert session.calls[0]["end"] == "2026-08-29T12"


def test_missing_api_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.delenv("eia_api_key", raising=False)

    session = FakeSession([rows(1)])

    with pytest.raises(RuntimeError, match="EIA_API_KEY"):
        pull_raw(session=session)

    # No request is attempted without a key.
    assert session.calls == []


def test_http_errors_are_not_suppressed_and_hide_the_key(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "super-secret-key")

    error = requests.HTTPError(
        "403 Client Error: Forbidden for url: "
        "https://api.eia.gov/v2/?api_key=super-secret-key"
    )
    session = FakeSession([FakeResponse([], status_error=error)])

    with pytest.raises(requests.HTTPError) as raised:
        pull_raw(session=session)

    assert "super-secret-key" not in str(raised.value)
    assert "***" in str(raised.value)


def test_unexpected_payload_shape_raises(monkeypatch):
    class BadResponse(FakeResponse):
        def json(self):
            return {"error": "something went wrong"}

    session = FakeSession([BadResponse([])])

    with pytest.raises(RuntimeError, match="Unexpected EIA response"):
        pull_raw(session=session)


def test_session_retries_transient_statuses():
    session = build_session()

    try:
        retry = session.get_adapter("https://api.eia.gov").max_retries

        assert retry.total == 5
        assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
        assert retry.backoff_factor > 0
    finally:
        session.close()
