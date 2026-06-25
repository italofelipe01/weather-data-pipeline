SELECT
  observation_date,
  state,
  city,
  avg(temperature_avg) AS daily_temperature_avg,
  min(temperature_min) AS daily_temperature_min,
  max(temperature_max) AS daily_temperature_max,
  avg(humidity_avg) AS daily_humidity_avg,
  sum(rain_1h_sum) AS daily_rain_sum,
  sum(sample_count) AS samples
FROM weather_hourly_observations
WHERE year = 2026
  AND month = 6
GROUP BY observation_date, state, city
ORDER BY observation_date, state, city;
