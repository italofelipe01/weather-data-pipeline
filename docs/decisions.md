# Decisoes tecnicas

## Lambda em vez de Airflow

Lambda atende melhor a uma coleta orientada a eventos, com custo quase zero quando o pipeline esta parado. Airflow seria mais pesado para esta etapa.

## SQS FIFO com uma mensagem por coleta

A fila desacopla planejamento e coleta e deduplica coletas iguais (inclusive invocacoes duplicadas do EventBridge). Cada mensagem e uma coleta inteira (um produto, 27 capitais); a Collector espaca as chamadas em 1,1 s e `ScalingConfig.MaximumConcurrency=2` limita a duas coletas simultaneas, o que mantem qualquer janela de 60 s abaixo do limite do plano Free. O visibility timeout e 6x o timeout da Collector, como a AWS recomenda.

## Um objeto por coleta, nao por capital

A primeira versao gravava um JSON por capital: ~445 mil PUTs/mes, o maior custo do projeto (~US$ 3,10/mes). Agrupar as 27 respostas de uma coleta num unico objeto reduz para ~16,5 mil PUTs/mes e tambem diminui GETs e LISTs da Curator. O leitor (`shared/raw_reader.py`) entende os dois formatos, entao os objetos antigos continuam validos ate expirarem.

## Coletas atrasadas sao descartadas

A OpenWeather sempre devolve o dado *atual*. Uma coleta reprocessada muito depois gravaria o valor de agora com o horario antigo, entao a Collector descarta snapshots acima de uma idade maxima por produto (15 min para a Current Weather) e conta em `SourceJobsExpired`.

## Somente o plano Free, usando tudo o que ele oferece

Alem de Current Weather e 5 Day / 3 Hour Forecast, o projeto usa a Air Pollution API (atual e previsao), que tambem faz parte do plano Free, e aproveita todos os campos documentados das respostas. One Call, History API e Air Pollution history ficam de fora.

## Teto de 50% aplicado pela Planner com contador gratuito

O parametro `MonthlyOperationalCallLimit` existia mas nao era aplicado. A Planner soma as chamadas que agenda num parametro SSM padrao (String, sem custo) e nao agenda coletas que ultrapassariam o teto. A primeira implementacao consultava a metrica do CloudWatch com `GetMetricData`, que e cobrada por metrica consultada; o contador no SSM tem o mesmo efeito por zero. Uma corrida rara entre duas execucoes da Planner pode subcontar algumas chamadas, o que a margem de 50% absorve. A metrica `OpenWeatherApiCalls` continua existindo para o dashboard de operacao (com retries).

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

## Modo offline com o mesmo codigo

O plano Free da AWS fecha a conta apos 6 meses. Para o projeto nao depender da nuvem, o modo offline reutiliza as mesmas funcoes com um agendador local, um S3 em disco e DuckDB no lugar do Athena. Manter um unico codigo evita que os dois modos divirjam; o layout de chaves identico permite migrar dados com `aws s3 sync`.

## Icones locais no dashboard

Os icones de condicao sao SVG gerados no proprio frontend em vez das imagens de `openweathermap.org`: o site nao faz nenhuma requisicao externa, funciona offline e a Content Security Policy fica restrita a `'self'`.

## pyarrow em layer

Antes todas as funcoes empacotavam pyarrow (~150 MB). Agora so a Curator recebe a layer; as demais tem ~200 KB, deploys menores e cold start mais rapido.
