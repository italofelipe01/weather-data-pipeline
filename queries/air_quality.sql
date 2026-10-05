-- Horas com qualidade do ar moderada ou pior (AQI >= 3) por capital e mes.
SELECT
  year,
  month,
  state,
  city,
  count_if(aqi >= 3) AS hours_moderate_or_worse,
  count_if(aqi >= 4) AS hours_poor_or_worse,
  count(aqi) AS hours_with_air_data,
  round(avg(pm2_5), 1) AS pm2_5_avg,
  max(pm2_5) AS pm2_5_max
FROM weather_hourly_observations
WHERE year = 2026
GROUP BY year, month, state, city
ORDER BY hours_moderate_or_worse DESC;
