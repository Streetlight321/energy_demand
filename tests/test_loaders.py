"""Loader tests. Supabase is faked; nothing here touches the network."""

import httpx
import pandas as pd
import pytest

import load.records as records
from load.load_bronze import BRONZE_BATCH_SIZE, load_bronze
from load.records import DEFAULT_BATCH_SIZE, to_records, upsert_records


class FakeQuery:
    def __init__(self, table, log, failures):
        self.table = table
        self.log = log
        self.failures = failures

    def upsert(self, batch, on_conflict=None):
        self.batch = batch
        self.on_conflict = on_conflict
        return self

    def execute(self):
        if self.failures and self.failures[0] > 0:
            self.failures[0] -= 1
            raise httpx.ReadTimeout("The read operation timed out")

        self.log.append(
            {
                "table": self.table,
                "on_conflict": self.on_conflict,
                "rows": len(self.batch),
                "batch": self.batch,
            }
        )
        return self


class FakeClient:
    """Records every upsert; can be told to time out the first N executes."""

    def __init__(self, failures=0):
        self.log = []
        self.failures = [failures]

    def table(self, name):
        return FakeQuery(name, self.log, self.failures)

    @property
    def rows_written(self):
        return sum(call["rows"] for call in self.log)


@pytest.fixture
def no_sleep(monkeypatch):
    delays = []
    monkeypatch.setattr("database.retry.time.sleep", delays.append)
    return delays


def stamp(index):
    """Walk forward in hours so a frame can be longer than a day."""
    return pd.Timestamp("2026-08-01T00", tz="UTC") + pd.Timedelta(hours=index)


def raw_frame(rows=10):
    return pd.DataFrame(
        [
            {
                "period": stamp(hour).strftime("%Y-%m-%dT%H"),
                "respondent": "CAL",
                "respondent-name": "California",
                "type": "D",
                "type-name": "Demand",
                "value": 1000 + hour,
                "value-units": "megawatthours",
            }
            for hour in range(rows)
        ]
    )


def silver_frame(rows=10):
    return pd.DataFrame(
        [
            {
                "period": stamp(hour),
                "respondent": "CAL",
                "demand_mwh": float(1000 + hour),
            }
            for hour in range(rows)
        ]
    )


# ---------- successful writes ----------

def test_batch_write_succeeds_and_reports_rows(no_sleep):
    client = FakeClient()

    written = upsert_records(
        silver_frame(5),
        table="silver_demand",
        conflict_key="period,respondent",
        label="demand",
        client=client,
    )

    assert written == 5
    assert client.rows_written == 5
    assert no_sleep == []


def test_large_frame_is_split_into_batches(no_sleep):
    client = FakeClient()

    upsert_records(
        silver_frame(600),
        table="silver_demand",
        conflict_key="period,respondent",
        label="demand",
        client=client,
    )

    assert [call["rows"] for call in client.log] == [250, 250, 100]
    assert client.rows_written == 600


def test_empty_frame_writes_nothing(no_sleep):
    client = FakeClient()

    assert upsert_records(
        pd.DataFrame(),
        table="silver_demand",
        conflict_key="period,respondent",
        label="demand",
        client=client,
    ) == 0
    assert client.log == []


# ---------- retry behaviour ----------

def test_timeout_then_successful_retry_writes_every_row(no_sleep):
    client = FakeClient(failures=1)

    written = upsert_records(
        silver_frame(5),
        table="silver_demand",
        conflict_key="period,respondent",
        label="demand",
        client=client,
    )

    assert written == 5
    assert client.rows_written == 5, "the retried batch must still land"
    assert no_sleep == [1.0]


def test_retry_replays_the_same_batch(no_sleep):
    """A replayed batch must be identical, or rows would be lost."""
    client = FakeClient(failures=2)

    upsert_records(
        silver_frame(3),
        table="silver_demand",
        conflict_key="period,respondent",
        label="demand",
        client=client,
    )

    assert len(client.log) == 1
    assert [row["respondent"] for row in client.log[0]["batch"]] == ["CAL"] * 3


def test_exhausted_retries_reraise(no_sleep):
    client = FakeClient(failures=99)

    with pytest.raises(httpx.ReadTimeout):
        upsert_records(
            silver_frame(3),
            table="silver_demand",
            conflict_key="period,respondent",
            label="demand",
            client=client,
            attempts=3,
        )

    assert client.log == []
    assert no_sleep == [1.0, 2.0]


# ---------- Bronze ----------

def test_bronze_default_batch_size_is_250():
    assert BRONZE_BATCH_SIZE == 250
    assert DEFAULT_BATCH_SIZE == 250


def test_bronze_batches_at_250_and_can_be_overridden(monkeypatch, no_sleep):
    client = FakeClient()
    monkeypatch.setattr(records, "supabase", client)

    load_bronze(raw_frame(600))
    assert [call["rows"] for call in client.log] == [250, 250, 100]

    client.log.clear()
    load_bronze(raw_frame(600), batch_size=100)
    assert [call["rows"] for call in client.log] == [100] * 6


def test_bronze_keeps_its_conflict_key_and_column_names(monkeypatch, no_sleep):
    client = FakeClient()
    monkeypatch.setattr(records, "supabase", client)

    load_bronze(raw_frame(2))

    call = client.log[0]
    assert call["table"] == "bronze_eia_region_data"
    assert call["on_conflict"] == "period,respondent,type"
    assert call["batch"][0] == {
        "period": "2026-08-01T00:00:00Z",
        "respondent": "CAL",
        "respondent_name": "California",
        "type": "D",
        "type_name": "Demand",
        "value": 1000,
        "value_units": "megawatthours",
    }


def test_bronze_survives_a_timeout_mid_load(monkeypatch, no_sleep):
    """The reported failure: a stall partway through a long Bronze load."""
    client = FakeClient()
    monkeypatch.setattr(records, "supabase", client)

    original_table = client.table
    state = {"calls": 0}

    def flaky_table(name):
        state["calls"] += 1
        # Time out once, on the second batch.
        client.failures[0] = 1 if state["calls"] == 2 else 0
        return original_table(name)

    monkeypatch.setattr(client, "table", flaky_table)

    written = load_bronze(raw_frame(600))

    assert written == 600
    assert client.rows_written == 600
    assert no_sleep == [1.0]


def test_bronze_upsert_is_idempotent_across_reruns(monkeypatch, no_sleep):
    client = FakeClient()
    monkeypatch.setattr(records, "supabase", client)

    frame = raw_frame(10)
    load_bronze(frame)
    first = list(client.log)

    client.log.clear()
    load_bronze(frame)

    assert [c["batch"] for c in client.log] == [c["batch"] for c in first]
    assert all(c["on_conflict"] == "period,respondent,type" for c in client.log)


def test_serialization_is_unchanged_by_the_shared_writer():
    """Bronze records must still be JSON-safe with None, not NaN."""
    frame = raw_frame(3)
    frame.loc[1, "value"] = None

    prepared = frame.rename(
        columns={
            "respondent-name": "respondent_name",
            "type-name": "type_name",
            "value-units": "value_units",
        }
    )
    prepared["value"] = pd.to_numeric(prepared["value"], errors="coerce")

    rows = to_records(prepared)

    assert rows[1]["value"] is None
    assert rows[0]["period"] == "2026-08-01T00:00:00Z"
