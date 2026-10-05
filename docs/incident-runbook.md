# Runbook de incidentes

Todos os alarmes publicam no topico SNS `<stack>-alerts` (e-mail definido em `BudgetAlertEmail`). Visao geral: dashboard CloudWatch `<stack>-operations` (output `OperationsDashboardUrl`).

## `<stack>-source-rejected` ou `<stack>-collector-errors`

Sintoma: a OpenWeather respondeu erro. Rejeitados (400/403/404, payload inesperado) sao descartados; falhas (401, 429, 5xx, timeout) voltam para a fila.

1. CloudWatch Logs Insights na Collector:

   ```text
   fields @timestamp, message, state, product, status_code, error
   | filter message in ["source_job_rejected", "source_job_failed"]
   | sort @timestamp desc
   | limit 50
   ```

2. `status_code = 401`: chave invalida ou ainda nao ativada.

   ```powershell
   ./scripts/set-openweather-key.ps1 -Environment dev -Region sa-east-1
   ```

   A Collector descarta a chave em cache no proximo 401; nao precisa redeploy.
3. `status_code = 429`: limite por minuto. Confirme se ha outro sistema usando a mesma chave; se necessario aumente `CurrentWeatherIntervalMinutes`.

## `<stack>-collection-stalled`

Nenhum snapshot gravado em 30 minutos com agenda ligada. Verifique, nesta ordem: regras do EventBridge habilitadas, erros da Planner (`<stack>-planner-errors`), alarme de teto mensal, mensagens na DLQ e logs da Collector.

## `<stack>-monthly-call-limit`

A Planner suspendeu coletas porque o teto mensal foi atingido. Elas voltam sozinhas no dia 1. Para liberar antes, aumente `MonthlyOperationalCallLimit` (maximo 500.000) ou reduza a cadencia. Para uma coleta pontual: `./scripts/invoke-planner.ps1 -Products current_weather -SkipBudgetCheck`.

## `<stack>-source-dlq-visible`

Mensagens que falharam 3 vezes. Inspecione:

```powershell
aws sqs receive-message --queue-url "<DeadLetterQueueUrl>" --max-number-of-messages 10 --region sa-east-1
```

Current Weather reprocessada tarde grava dados do momento do reprocessamento; normalmente e melhor descartar (`aws sqs purge-queue --queue-url "<DeadLetterQueueUrl>"`). Previsoes e qualidade do ar podem ser coletadas de novo com `./scripts/invoke-planner.ps1 -Products forecast_5d_3h,air_pollution`.

## `<stack>-curator-errors`

A proxima execucao recupera as horas faltantes das ultimas 6 horas. Para periodos maiores (dentro da retencao do raw):

```powershell
./scripts/invoke-curator.ps1 -StartHour "2026-06-24T00:00:00Z" -EndHour "2026-06-25T23:00:00Z" -RebuildServing
```

## `<stack>-publisher-errors`

O dashboard continua mostrando o ultimo `data/latest.json`. Verifique os logs da Publisher e rode `./scripts/invoke-publisher.ps1`.

## Dashboard desatualizado

O frontend mostra um aviso quando a observacao mais recente tem mais de 45 minutos. Verifique se `EnableSchedules=true` e se os alarmes acima estao em OK. Para republicar so o site: `./scripts/publish-frontend.ps1`.

## Localizar uma coleta

Procure por `state`, `product` e `snapshot_at` nos logs da Collector (`source_job_processed` traz `s3_key`).
