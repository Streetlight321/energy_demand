-- Optional observability table. Nothing in the pipeline writes to it yet;
-- it is here so run history can be added later without a schema scramble.

create table if not exists public.pipeline_runs (
    id bigint generated always as identity primary key,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    status text not null default 'running',
    ingestion_start text,
    rows_extracted integer,
    bronze_rows integer,
    demand_rows integer,
    generation_rows integer,
    interchange_rows integer,
    error_message text
);

create index if not exists pipeline_runs_started_at_idx
    on public.pipeline_runs (started_at desc);
