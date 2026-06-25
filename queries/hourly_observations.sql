SELECT
  observation_date,
  observation_hour,
  state,
  city,
  temperature_avg,
  humidity_avg,
  pressure_avg,
  wind_speed_avg,
  rain_1h_sum,
  sample_count
FROM weather_hourly_observations
WHERE year = 2026
  AND month = 6
  AND day = 25
ORDER BY state, city, observation_hour;
