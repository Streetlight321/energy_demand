-- Sanity checks / example analytics against the Gold layer.

-- 1. Highest peak-demand region-days.
select
    date,
    respondent,
    respondent_name,
    peak_demand_mwh
from gold_demand_daily
order by peak_demand_mwh desc
limit 20;

-- 2. Best day-ahead forecast accuracy (lower MAPE is better).
--    Weighted by observations so a sparse day cannot dominate.
select
    respondent,
    sum(mape_pct * observation_count) / nullif(sum(observation_count), 0)
        as avg_mape_pct,
    sum(observation_count) as observations
from gold_forecast_performance_daily
where mape_pct is not null
group by respondent
order by avg_mape_pct;

-- 3. Forecast bias: positive = actual demand exceeded the forecast.
select
    respondent,
    avg(forecast_bias_mwh) as avg_bias_mwh
from gold_forecast_performance_daily
group by respondent
order by avg_bias_mwh desc;

-- 4. Generation vs demand, most recent hours first.
select
    period,
    respondent,
    demand_mwh,
    net_generation_mwh,
    generation_minus_demand_mwh
from gold_grid_balance_hourly
order by period desc
limit 100;

-- 5. Dashboard latest state.
select *
from gold_regional_summary
order by latest_demand_mwh desc nulls last;

-- 6. Grain checks: each of these must return zero rows.
select date, respondent, count(*)
from gold_demand_daily
group by date, respondent
having count(*) > 1;

select period, respondent, count(*)
from gold_grid_balance_hourly
group by period, respondent
having count(*) > 1;

-- 7. Gold daily coverage should not exceed 24 observations per region-day.
select date, respondent, observation_count
from gold_demand_daily
where observation_count > 24;
