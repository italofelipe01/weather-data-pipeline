-- Resumo mensal por capital a partir da tabela diaria (datas locais).
SELECT
  year,
  month,
  state,
  city,
  round(avg(temperature_avg), 2) AS monthly_temperature_avg,
  min(temperature_min) AS monthly_temperature_min,
  max(temperature_max) AS monthly_temperature_max,
  round(avg(humidity_avg), 1) AS monthly_humidity_avg,
  round(sum(rain_mm), 1) AS monthly_rain_mm,
  count_if(rain_mm >= 1) AS rain_days,
  round(avg(aqi_avg), 2) AS monthly_aqi_avg,
  count(*) AS days_observed
FROM weather_daily_observations
WHERE year = 2026
GROUP BY year, month, state, city
ORDER BY year, month, state;
