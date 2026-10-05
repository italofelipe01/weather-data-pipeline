# Arquitetura

O pipeline coleta snapshots recorrentes de clima atual, previsao e qualidade do ar das 27 capitais brasileiras, consolida em tabelas Parquet e publica um dashboard estatico.

## Fluxo

1. **EventBridge** dispara a Lambda **Planner** em quatro agendas (Current Weather a cada `CurrentWeatherIntervalMinutes`, Forecast no minuto 05, Air Pollution no minuto 35 e Air Pollution forecast a cada 6 horas no minuto 50).
2. A **Planner** cria um job por capital e produto, consulta a metrica `OpenWeatherApiCalls` do mes e **suspende a coleta** se o teto `MonthlyOperationalCallLimit` seria ultrapassado. Os jobs vao para a **SQS FIFO** em lotes de 10, com `MessageGroupId` por UF e `MessageDeduplicationId` derivado do conteudo.
3. A **Collector** consome a fila (lotes de 5, no maximo 2 execucoes simultaneas), le a chave no **SSM** (cache de 5 minutos, descartado em HTTP 401), chama a OpenWeather e grava o JSON bruto no S3 com chave deterministica e `If-None-Match: *`. Partial batch response: so os itens com falha voltam para a fila; apos 3 tentativas vao para a **DLQ**.
4. A **Curator** roda no minuto 20 de cada hora:
   - verifica as ultimas `CURATOR_LOOKBACK_HOURS` (6) horas e reconstroi as que nao tem arquivo curado (catch-up automatico);
   - gera a tabela horaria (Current Weather + Air Pollution) e a tabela de previsoes emitidas na hora;
   - gera o agregado diario de cada data local ja encerrada (e refaz dias afetados por horas reprocessadas);
   - publica `data/hourly/<uf>.json` (7 dias), `data/daily/<uf>.json` (ate 730 dias) e `data/forecast/<uf>.json` no bucket do site.
5. A **Publisher** roda a cada 10 minutos e grava `data/latest.json` com a observacao e a qualidade do ar mais recentes de cada capital e o consumo mensal da API.
6. **CloudFront** (Origin Access Control) serve o bucket do site; `data/*` tem TTL curto.
7. **Glue Data Catalog** (partition projection) e **Athena** consultam as tabelas curadas sem crawler.
8. **CloudWatch** recebe metricas EMF das Lambdas; alarmes notificam o topico **SNS** (e-mail opcional). Um dashboard `<stack>-operations` resume chamadas, falhas, filas e duracao.

## Lambdas

| Funcao | Gatilho | Memoria / timeout | Dependencias |
|---|---|---|---|
| Planner | EventBridge (4 agendas) | 256 MB / 60 s | boto3 do runtime |
| Collector | SQS FIFO | 256 MB / 60 s | boto3 do runtime |
| Curator | EventBridge (hora:20) | 1024 MB / 300 s | layer `AnalyticsLayer` (pyarrow) |
| Publisher | EventBridge (10 min) | 256 MB / 120 s | boto3 do runtime |

Somente a Curator recebe a layer com pyarrow; as demais ficam com ~200 KB e cold start curto. O teste `tests/unit/test_packaging.py` garante que Planner, Collector e Publisher nao importam pyarrow.

## Eventos manuais

| Lambda | Evento | Efeito |
|---|---|---|
| Planner | `{"products": "all", "states": ["SP"]}` | coleta imediata; `skip_budget_check` ignora o teto |
| Curator | `{}` | horas faltantes das ultimas 6 h + diarios + series |
| Curator | `{"target_hour": "..."}` | reprocessa uma hora |
| Curator | `{"start_hour": "...", "end_hour": "..."}` | backfill de ate 744 horas (dentro da retencao do raw) |
| Curator | `{"rebuild_serving": true}` | refaz as series diarias do dashboard a partir dos Parquet |
| Curator | `{"publish": false}` | nao toca no bucket do site |
| Publisher | `{}` | republica `data/latest.json` |

Exemplos em `events/`.

## Seguranca

- Buckets privados, criptografia SSE-S3 e politica que nega trafego sem TLS.
- CloudFront acessa o bucket do site por OAC; cabecalhos de seguranca (CSP, HSTS, X-Frame-Options, nosniff).
- IAM por funcao com o minimo necessario (`raw/*` para a Collector, `curated/*` e `data/*` para a Curator, `data/*` para a Publisher).
- A chave da OpenWeather fica apenas no SSM SecureString; nunca e logada e nao aparece em tracebacks.
