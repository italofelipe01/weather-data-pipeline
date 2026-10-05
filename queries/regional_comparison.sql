-- Comparativo semanal por regiao (media das capitais).
SELECT
  date_trunc('week', observation_date) AS week_start,
  region,
  round(avg(temperature_avg), 2) AS temperature_avg,
  round(avg(humidity_avg), 1) AS humidity_avg,
  round(avg(rain_mm), 1) AS rain_mm_per_capital_day,
  round(avg(pm2_5_avg), 1) AS pm2_5_avg
FROM weather_daily_observations
WHERE year = 2026
GROUP BY 1, 2
ORDER BY 1, 2;
