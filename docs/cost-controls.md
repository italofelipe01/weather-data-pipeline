# Controle de custo

Meta: operar com folga dentro de US$ 100 de credito por seis meses.

## Teto da OpenWeather

```text
1.000.000 chamadas/mes * 50% = 500.000 chamadas/mes (MonthlyOperationalCallLimit)
cadencia padrao: 445.284 chamadas em 31 dias
```

A Planner soma a metrica `OpenWeatherApiCalls` do mes (CloudWatch `GetMetricData`, cache de 5 minutos por container) e nao enfileira jobs que ultrapassariam o teto. Quando isso acontece, emite `CollectionJobsSkipped` e o alarme `<stack>-monthly-call-limit` envia e-mail. Se o CloudWatch estiver indisponivel a Planner segue coletando (o teto ja e metade do limite real).

## Estimativa mensal (sa-east-1, cadencia padrao)

| Item | Volume aproximado | Custo |
|---|---|---|
| S3 PUT do raw | ~445 mil objetos | ~US$ 3,10 |
| S3 GET/LIST (Curator e Publisher) | ~300 mil GET, ~80 mil LIST/PUT | ~US$ 0,70 |
| S3 armazenamento | raw com 30 dias + curated | < US$ 0,10 |
| SQS FIFO | ~1,4 milhao de requisicoes | ~US$ 0,20 |
| Lambda | ~180 mil invocacoes, ~30 mil GB-s | Free Tier |
| CloudWatch Logs | < 1 GB | Free Tier |
| CloudWatch metricas / alarmes / dashboard | 8 metricas, 9 alarmes, 1 dashboard | Free Tier |
| CloudWatch GetMetricData | ~25 mil metricas consultadas | ~US$ 0,25 |
| CloudFront | uso pessoal | Free Tier (1 TB, 10 M requisicoes) |
| Glue Catalog | 1 banco, 3 tabelas | Free Tier |
| Athena | US$ 5 por TB lido, limite de 1 GB por consulta | centavos |
| **Total** | | **~US$ 4 a 5 / mes** |

Os PUTs do raw sao o principal custo. Alavancas:

- `CurrentWeatherIntervalMinutes=5` reduz a Current Weather para ~241 mil chamadas/mes (~US$ 1,70 de PUT);
- `EnableAirPollution=false` remove ~23 mil chamadas/mes;
- `EnableAnalytics=false` e `EnableFrontend=false` removem Glue/Athena e CloudFront (custo ocioso ja e zero).

## Medidas de controle

- Schedules desabilitados por padrao (`EnableSchedules=false`).
- Teto mensal de chamadas aplicado no codigo, nao so documentado.
- `raw/` expira em 30 dias; `athena-results/` e `tmp/` em 7 dias; uploads incompletos em 1 dia.
- Logs com retencao de 7 dias.
- pyarrow apenas na Curator (layer), reduzindo pacote e cold start das demais funcoes.
- Sem NAT Gateway, RDS, ECS, MSK, Glue crawler ou servidores permanentes.
- Budget mensal opcional (`BudgetAlertEmail`, padrao US$ 10) com alertas em 50%, 80% e previsao de 100%.
- Metricas e alarmes dimensionados para caber no Free Tier do CloudWatch (10 metricas, 10 alarmes).

Antes de habilitar agenda, confirme no painel da OpenWeather que a conta esta no plano Free e que a chave ja esta ativa. O e-mail do Budget e o do SNS precisam ser confirmados quando a AWS enviar a inscricao.
