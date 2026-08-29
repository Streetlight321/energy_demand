-- Gold analytics tables. Run once in the Supabase SQL editor.
-- Bronze and Silver are unchanged and not recreated here.

create table if not exists public.gold_demand_daily (
    date date not null,
    respondent text not null,
    respondent_name text,
    avg_demand_mwh numeric,
    peak_demand_mwh numeric,
    min_demand_mwh numeric,
    demand_stddev_mwh numeric,
    observation_count integer,
    transformed_at timestamptz not null default now(),
    primary key (date, respondent)
);

create table if not exists public.gold_forecast_performance_daily (
    date date not null,
    respondent text not null,
    respondent_name text,
    mae_mwh numeric,
    rmse_mwh numeric,
    mape_pct numeric,
    forecast_bias_mwh numeric,
    max_abs_error_mwh numeric,
    observation_count integer,
    transformed_at timestamptz not null default now(),
    primary key (date, respondent)
);

create table if not exists public.gold_grid_balance_hourly (
    period timestamptz not null,
    respondent text not null,
    respondent_name text,
    demand_mwh numeric,
    net_generation_mwh numeric,
    total_interchange_mwh numeric,
    generation_minus_demand_mwh numeric,
    transformed_at timestamptz not null default now(),
    primary key (period, respondent)
);

create table if not exists public.gold_regional_summary (
    respondent text primary key,
    respondent_name text,
    latest_period timestamptz,
    latest_demand_mwh numeric,
    latest_forecast_demand_mwh numeric,
    latest_net_generation_mwh numeric,
    latest_total_interchange_mwh numeric,
    recent_forecast_mape_pct numeric,
    recent_forecast_bias_mwh numeric,
    transformed_at timestamptz not null default now()
);

-- Dashboard reads are almost always "recent rows for a region".
create index if not exists gold_demand_daily_date_idx
    on public.gold_demand_daily (date desc);

create index if not exists gold_forecast_performance_daily_date_idx
    on public.gold_forecast_performance_daily (date desc);

create index if not exists gold_grid_balance_hourly_period_idx
    on public.gold_grid_balance_hourly (period desc);
