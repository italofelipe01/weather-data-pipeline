# Proximas etapas

Depois que a fonte raw estiver validada:

1. Converter `curated/hourly_observations/` de CSV para Parquet.
2. Criar agregados diarios e mensais a partir da tabela horaria.
3. Criar Glue Data Catalog.
4. Criar Athena Workgroup e queries analiticas.
5. Adicionar testes PySpark para schema, particionamento e metricas climaticas.
6. Criar dashboard ou notebooks apenas depois da camada curated estabilizada.
