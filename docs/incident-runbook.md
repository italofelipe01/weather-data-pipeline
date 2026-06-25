# Runbook de incidentes

## Chave ausente ou invalida

Sintoma: Collector falha ao ler SSM ou OpenWeather retorna 401.

Acao:

```powershell
./scripts/set-openweather-key.ps1 -ApiKey "<OPENWEATHER_API_KEY>" -Environment dev -Region sa-east-1
```

## Limite excedido

Sintoma: OpenWeather retorna 429.

Acao: desabilite os schedules, aguarde a janela de limite e reduza a frequencia se necessario.

## Inspecionar DLQ

```powershell
aws sqs receive-message --queue-url "<DeadLetterQueueUrl>" --max-number-of-messages 10
```

## Localizar uma coleta

Procure por `state`, `city`, `product` e `snapshot_at` nos logs da Collector no CloudWatch.
