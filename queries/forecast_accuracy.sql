-- Erro da previsao de temperatura por antecedencia: compara cada previsao 3 h com a media
-- observada na hora prevista. bias > 0 = previsao mais quente que o observado.
WITH forecasts AS (
  SELECT state, city, forecast_time, lead_hours, temperature AS forecast_temperature, pop
  FROM weather_forecast_3h
  WHERE year = 2026 AND month = 10
),
observed AS (
  SELECT state, observation_timestamp, temperature_avg, rain_mm
  FROM weather_hourly_observations
  WHERE year = 2026 AND month IN (10, 11)
)
SELECT
  f.state,
  f.city,
  CAST(floor(f.lead_hours / 24) AS integer) AS lead_days,
  count(*) AS pairs,
  round(avg(f.forecast_temperature - o.temperature_avg), 2) AS bias_c,
  round(avg(abs(f.forecast_temperature - o.temperature_avg)), 2) AS mae_c,
  round(avg(f.pop), 2) AS mean_pop,
  round(avg(CASE WHEN o.rain_mm > 0 THEN 1.0 ELSE 0.0 END), 2) AS observed_rain_frequency
FROM forecasts f
JOIN observed o
  ON o.state = f.state
 AND o.observation_timestamp = f.forecast_time
GROUP BY 1, 2, 3
ORDER BY 1, 3;
