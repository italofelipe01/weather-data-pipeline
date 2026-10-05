# Decisoes tecnicas

## Lambda em vez de Airflow

Lambda atende melhor a uma coleta orientada a eventos, com custo quase zero quando o pipeline esta parado. Airflow seria mais pesado para esta etapa.

## SQS FIFO com concorrencia limitada

A fila desacopla planejamento e coleta e deduplica jobs iguais (inclusive invocacoes duplicadas do EventBridge). `ScalingConfig.MaximumConcurrency=2` mantem as rajadas abaixo de 60 chamadas/minuto, e o visibility timeout e 6x o timeout da Collector, como a AWS recomenda.

## Somente o plano Free, usando tudo o que ele oferece

Alem de Current Weather e 5 Day / 3 Hour Forecast, o projeto usa a Air Pollution API (atual e previsao), que tambem faz parte do plano Free, e aproveita todos os campos documentados das respostas. One Call, History API e Air Pollution history ficam de fora.

## Teto de 50% aplicado pela Planner

O parametro `MonthlyOperationalCallLimit` existia mas nao era aplicado. Agora a Collector publica `OpenWeatherApiCalls` (toda requisicao conta, com ou sem sucesso) e a Planner consulta o total do mes antes de enfileirar. Contadores em DynamoDB ou SSM foram descartados: a metrica ja existe, nao precisa de recurso novo e o atraso de alguns minutos e irrelevante diante da margem de 50%.

## Metricas EMF direto no stdout

O runtime Python do Lambda prefixa registros do `logging` com nivel, data e request id, o que impede o CloudWatch de extrair metricas no formato EMF. As metricas agora sao escritas como uma linha JSON pura no stdout. Todas usam a dimensao unica `Pipeline` para caber no Free Tier.

## Agregacoes corretas para dados da OpenWeather

- Chuva: `rain.1h` e intensidade (mm/h); a hora usa a media, o dia soma as horas.
- Observacoes repetidas (mesmo `dt`) contam uma vez.
- Minima e maxima sao extremos temporais das observacoes.
- Dias usam a data local de cada capital, com offset fixo (o Brasil nao tem horario de verao desde 2019), sem depender de tzdata no runtime.

## S3 como raw zone e Parquet como camada curada

O S3 e barato, duravel e adequado para Athena. O raw expira em 30 dias; as tabelas Parquet (Snappy) sao a camada de longo prazo, com um arquivo por hora (todas as capitais) e um por dia.

## Catch-up automatico em vez de agenda rigida

A Curator nao processa apenas "a hora anterior": ela verifica as ultimas 6 horas e reconstroi as que faltam, refaz os diarios afetados e aceita intervalos para backfill. Uma falha pontual se corrige sozinha na execucao seguinte.

## Dashboard estatico alimentado por JSON pre-calculado

Em vez de API Gateway + Lambda consultando Athena a cada acesso, a Curator e a Publisher gravam documentos JSON pequenos (`data/*.json`) no bucket do site, servido pelo CloudFront com OAC. O custo por visita e zero, nao ha servidor e o site continua funcionando com o ultimo dado publicado mesmo se o pipeline parar. O frontend nao tem build nem dependencias externas.

## Glue com partition projection

As tabelas do Athena usam partition projection: nao ha crawler, nem `MSCK REPAIR`, nem custo ocioso. O workgroup limita cada consulta a 1 GB lido. Isso substitui a decisao anterior de adiar Glue/Athena, porque agora ha dados curados e o custo ocioso e zero.

## SSM Parameter Store

A chave OpenWeather fica em SecureString no SSM. Secrets Manager nao foi usado para evitar custo adicional, e rotacao automatica nao e requisito. A Collector descarta o cache da chave ao receber HTTP 401, entao uma troca de chave vale em minutos, sem redeploy.

## Sem DynamoDB

A idempotencia e resolvida pela deduplicacao da SQS FIFO e pela chave deterministica no S3 com `If-None-Match`.

## pyarrow em layer

Antes todas as funcoes empacotavam pyarrow (~150 MB). Agora so a Curator recebe a layer; as demais tem ~200 KB, deploys menores e cold start mais rapido.
