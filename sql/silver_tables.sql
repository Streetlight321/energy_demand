-- Silver domain tables. Run once in the Supabase SQL editor.
-- Bronze (bronze_eia_region_data) is unchanged and not recreated here.

create table if not exists public.silver_demand (
    period timestamptz not null,
    respondent text not null,
    respondent_name text,
    demand_mwh numeric,
    forecast_demand_mwh numeric,
    forecast_error_mwh numeric,
    forecast_error_pct numeric,
    transformed_at timestamptz not null default now(),
    primary key (period, respondent)
);

create table if not exists public.silver_generation (
    period timestamptz not null,
    respondent text not null,
    respondent_name text,
    net_generation_mwh numeric,
    transformed_at timestamptz not null default now(),
    primary key (period, respondent)
);

create table if not exists public.silver_interchange (
    period timestamptz not null,
    respondent text not null,
    respondent_name text,
    total_interchange_mwh numeric,
    transformed_at timestamptz not null default now(),
    primary key (period, respondent)
);
