-- Linhas horarias de um dia (UTC) para todas as capitais.
-- Workgroup: <StackName>; banco: weather_<environment>.
SELECT
  observation_timestamp,
  local_date,
  local_hour,
  state,
  city,
  temperature_avg,
  temperature_min,
  temperature_max,
  humidity_avg,
  pressure_avg,
  wind_speed_avg,
  rain_mm,
  aqi,
  pm2_5,
  observation_count
FROM weather_hourly_observations
WHERE year = 2026
  AND month = 10
  AND day = 5
ORDER BY state, observation_timestamp;
