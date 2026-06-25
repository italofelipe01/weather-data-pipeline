-- Consulta futura para Athena, apos catalogar a camada raw ou curated.
-- Inventario de snapshots coletados por produto e capital.
SELECT
  product,
  state,
  city,
  min(snapshot_at) AS first_snapshot_at,
  max(snapshot_at) AS last_snapshot_at,
  count(*) AS snapshots_collected
FROM weather_source_snapshots
GROUP BY product, state, city
ORDER BY product, state, city;
