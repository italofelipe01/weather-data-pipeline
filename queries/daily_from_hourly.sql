-- Agregado diario por data LOCAL calculado direto da tabela horaria
-- (a Curator ja grava esse resultado em weather_daily_observations).
-- Chuva: rain_mm de cada hora ja e mm na hora; o dia e a soma.
SELECT
  local_date,
  state,
  city,
  round(avg(temperature_avg), 2) AS daily_temperature_avg,
  min(temperature_min) AS daily_temperature_min,
  max(temperature_max) AS daily_temperature_max,
  round(avg(humidity_avg), 1) AS daily_humidity_avg,
  round(sum(rain_mm), 2) AS daily_rain_mm,
  count(*) AS hours_observed
FROM weather_hourly_observations
WHERE year = 2026
  AND month = 10
GROUP BY local_date, state, city
ORDER BY local_date, state;
