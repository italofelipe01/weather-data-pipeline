# Arquitetura

O pipeline coleta snapshots recorrentes de clima atual e previsao das capitais brasileiras.

Fluxo:

1. EventBridge ou operador invoca a Lambda Planner.
2. A Planner cria um job por capital e produto OpenWeather.
3. A SQS FIFO desacopla os jobs e evita duplicidade no intervalo de deduplicacao.
4. A Collector le a chave da OpenWeather no SSM.
5. A Collector chama Current Weather API ou 5 Day / 3 Hour Forecast API.
6. A resposta raw e gravada no S3 com chave particionada por produto, UF, cidade e hora.
7. Falhas transitorias retornam para retry; apos tres tentativas vao para DLQ.
8. A Curator consolida a hora fechada de `current_weather` em CSV tabular em `curated/hourly_observations/`.

A etapa analitica seguinte deve converter a camada horaria para Parquet e derivar agregados diarios e mensais.
