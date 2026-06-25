# Estrategia de armazenamento

O objetivo e evitar que o S3 vire um deposito permanente de milhoes de JSONs pequenos.

## Camadas

```text
raw/
  snapshots brutos recebidos da OpenWeather
  retencao curta: 30 dias por padrao

curated/
  arquivos tabulares e agregados
  retencao longa na proxima etapa
```

## Por que expirar raw

Com a cadencia padrao, o pipeline pode gerar cerca de 408.240 objetos por mes. Em seis meses isso passa de 2,4 milhoes de objetos se nada for expirado. O tamanho em GB tende a ser baixo, mas muitos objetos pequenos pioram listagem, manutencao e consultas futuras.

## Tabela horaria atual

A Lambda Curator ja cria a primeira tabela horaria em CSV:

```text
curated/hourly_observations/year=<yyyy>/month=<mm>/day=<dd>/hour=<hh>/weather_hourly_observations_<timestamp>.csv
```

Essa tabela tem colunas separadas para `observation_date`, `observation_hour`, `year`, `month`, `day`, `city`, `state`, `temperature_avg`, `humidity_avg`, `rain_1h_sum` e demais metricas.

## Proxima etapa recomendada

Converter a tabela horaria para Parquet e criar agregados diarios:

```text
curated/hourly_observations_parquet/year=<yyyy>/month=<mm>/day=<dd>/hour=<hh>/part-000.parquet
curated/daily_observations/year=<yyyy>/month=<mm>/day=<dd>/part-000.parquet
```

Preferencia:

- um arquivo por hora contendo todas as capitais;
- um arquivo por dia contendo agregados diarios;
- Parquet com compressao Snappy;
- particionamento por data e produto.

## Politica atual

O `template.yaml` define `RawDataRetentionDays=30` por padrao. Isso preserva uma janela suficiente para depuracao sem deixar o custo e o numero de objetos crescerem sem limite.
