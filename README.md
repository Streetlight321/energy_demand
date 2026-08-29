# energy_demand

Hourly U.S. EIA electricity region data, ingested into Supabase with a
Bronze → Silver → Gold medallion architecture.

## Layout

```text
database/client.py        shared Supabase client (single source of config)
database/queries.py       checkpoint reads -> get_latest_bronze_period()
extract/pull_data.py      EIA API access only: retries + pagination
extract/window.py         ingestion window arithmetic (lookback, catch-up cap)
transform/                pure DataFrame -> DataFrame transformations
    common.py             raw column normalization helpers
    validation.py         shared Silver data-quality checks
    demand.py             transform_demand / validate_demand
    generation.py         transform_generation / validate_generation
    interchange.py        transform_interchange / validate_interchange
load/                     database writes only
    load_bronze.py        bronze_eia_region_data (period, respondent, type)
    silver_writer.py      shared batched Silver upsert
    load_demand.py        silver_demand
    load_generation.py    silver_generation
    load_interchange.py   silver_interchange
transform/gold/           Silver -> Gold aggregates (pure DataFrame code)
    demand_daily.py       gold_demand_daily
    forecast_performance.py   gold_forecast_performance_daily
    grid_balance.py       gold_grid_balance_hourly
    regional_summary.py   gold_regional_summary
load/records.py           shared serialization + batched upsert
load/gold/                Gold writes only
scripts/backfill.py       manual historical load (never runs on a schedule)
sql/silver_tables.sql     Silver DDL (run once in the Supabase SQL editor)
sql/gold_tables.sql       Gold DDL (run once in the Supabase SQL editor)
sql/gold_analytics_examples.sql   example analytics + grain sanity checks
sql/pipeline_runs.sql     optional run-history table (not wired up yet)
tests/                    unit tests, no API key or database required
pipeline.py               production orchestration
.github/workflows/        hourly schedule + test CI
```

## Ingestion flow

```text
latest Bronze period  ->  minus 48h lookback  ->  paginated EIA query
                      ->  upsert Bronze  ->  transform  ->  upsert Silver
                      ->  aggregate Gold  ->  upsert Gold
```

The 48-hour lookback is deliberate: the EIA revises recent hours and backfills
late-arriving records, so every run re-reads the trailing window. All writes
are upserts, so re-processing the same window changes nothing.

If Bronze is empty the scheduled run fails with a clear message instead of
pulling years of history; use the backfill script for that. If Bronze is more
than a week behind, a single run is capped at a 7-day catch-up window.

## Tables

| Layer  | Table                    | Grain                          |
| ------ | ------------------------ | ------------------------------ |
| Bronze | `bronze_eia_region_data` | period + respondent + type     |
| Silver | `silver_demand`          | period + respondent (`D`,`DF`) |
| Silver | `silver_generation`      | period + respondent (`NG`)     |
| Silver | `silver_interchange`     | period + respondent (`TI`)     |
| Gold   | `gold_demand_daily`      | date + respondent              |
| Gold   | `gold_forecast_performance_daily` | date + respondent     |
| Gold   | `gold_grid_balance_hourly` | period + respondent          |
| Gold   | `gold_regional_summary`  | respondent                     |

`forecast_error_mwh = demand_mwh - forecast_demand_mwh`, so a positive error
means actual demand exceeded the day-ahead forecast. `forecast_error_pct` is
only computed against a positive actual demand; it is null when demand is
zero or negative, where a percentage would be infinite or sign-flipped.

## Gold layer

Gold is business-ready analytics, recomputed only for the window the run
touched:

- **`gold_demand_daily`** — daily mean / peak / min / stddev demand. Hourly
  demand is a rate, so there is deliberately no "daily total" sum.
- **`gold_forecast_performance_daily`** — MAE, RMSE, MAPE, signed bias and max
  absolute error, recomputed from actual and forecast demand rather than
  averaged from Silver's percentage column. MAPE excludes zero-demand hours.
- **`gold_grid_balance_hourly`** — demand, generation and interchange joined
  per hour, plus `generation_minus_demand_mwh`. Missing measurements stay
  null; the metric is named after its arithmetic rather than being labelled
  surplus/deficit or import/export.
- **`gold_regional_summary`** — one row per region: the values recorded at
  that region's latest hour, plus observation-weighted MAPE and bias over the
  last 7 available days.

Daily Gold is keyed by calendar date, so a window starting mid-day would
otherwise overwrite a full day's aggregate with a partial one. The pipeline
back-reads only the missing head of that first day from `silver_demand`
before aggregating. The trailing day stays partial on purpose — it is still
accumulating and the next run recomputes it.

## Validation policy

Structural problems raise `SilverValidationError` and stop the run: missing
columns, null `period` / `respondent`, or a broken `(period, respondent)`
grain. Value anomalies are logged and loaded as reported — the EIA does emit
occasional negative hourly demand for small balancing authorities (e.g. SEC),
and a pipeline that already wrote Bronze should not abort over it.

## Running

```bash
uv sync
uv run pipeline.py                  # incremental run (48h lookback)
uv run pytest tests                 # offline unit tests

# Historical backfill — manual only
uv run scripts/backfill.py
uv run scripts/backfill.py --start 2024-01-01T00 --end 2024-06-30T23
uv run scripts/backfill.py --chunk-days 7
```

## Scheduling

`.github/workflows/energy_pipeline.yml` runs `uv run pipeline.py` at 15 past
every hour. It needs three repository secrets: `EIA_API_KEY`, `SUPABASE_URL`,
`SUPABASE_KEY`.

Credentials are read from `.env` locally (git-ignored) and from repository
secrets in CI. The EIA key is accepted as `EIA_API_KEY` or the legacy
lowercase `eia_api_key`; it is never printed, and it is redacted out of HTTP
error messages.
