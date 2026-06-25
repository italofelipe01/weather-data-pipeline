SELECT
  year,
  month,
  state,
  city,
  avg(temperature_avg) AS monthly_temperature_avg,
  min(temperature_min) AS monthly_temperature_min,
  max(temperature_max) AS monthly_temperature_max,
  avg(humidity_avg) AS monthly_humidity_avg,
  sum(rain_1h_sum) AS monthly_rain_sum,
  sum(sample_count) AS samples
FROM weather_hourly_observations
WHERE year = 2026
GROUP BY year, month, state, city
ORDER BY year, month, state, city;
