-- Cobertura da coleta: horas curadas e observacoes distintas por capital e dia (UTC).
SELECT
  observation_date,
  state,
  city,
  count(*) AS hours_curated,
  sum(sample_count) AS snapshots,
  sum(observation_count) AS distinct_observations,
  sum(air_sample_count) AS air_snapshots
FROM weather_hourly_observations
WHERE year = 2026
  AND month = 10
GROUP BY observation_date, state, city
HAVING count(*) < 24
ORDER BY observation_date, state;
