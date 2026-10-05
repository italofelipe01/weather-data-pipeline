# Modo offline (sem nuvem)

O modo offline roda **o mesmo codigo** da AWS na sua maquina: coleta na mesma cadencia, curadoria com recuperacao de horas perdidas, agregados diarios, publicacao e o dashboard. Nao precisa de conta AWS; so da chave da OpenWeather e de internet para as chamadas a API.

| | AWS | Offline |
|---|---|---|
| Agendamento | EventBridge | `scripts/offline_service.py` (laco interno) |
| Coleta | Lambda Collector via SQS | mesma funcao `collect_batch`, em sequencia |
| Armazenamento | S3 | pasta `.local-data/lake/` (mesmo layout de chaves) |
| Teto mensal | parametro SSM | `.local-data/state/call-counter.json` |
| Dashboard | CloudFront | `http://localhost:8000` |
| Consultas | Athena | DuckDB (`scripts/query_local.py`, mesmo SQL) |
| Alertas | CloudWatch + SNS | log em `.local-data/logs/offline-service.log` |

## Opcao 1: PowerShell / Python (Windows, macOS, Linux)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-offline.txt
Copy-Item .env.example .env        # preencha OPENWEATHER_API_KEY
./scripts/start-offline.ps1        # roda ate Ctrl+C; dashboard em http://localhost:8000
```

Opcoes: `-IntervalMinutes 5`, `-States SP,RJ`, `-NoAirPollution`, `-RawRetentionDays 0` (nunca apagar o raw), `-Lan` (abrir o dashboard para outros dispositivos da rede).

Sem PowerShell: `python scripts/offline_service.py --help`.

### Iniciar sozinho com o Windows

```powershell
./scripts/install-offline-service.ps1              # cria a tarefa agendada (ao fazer logon), oculta, reinicia se cair
./scripts/install-offline-service.ps1 -Uninstall   # remove
```

## Opcao 2: Docker (24/7, qualquer sistema)

```powershell
Copy-Item .env.example .env        # preencha OPENWEATHER_API_KEY
docker compose up -d               # http://localhost:8000
docker compose logs -f weather     # acompanhar
docker compose down                # parar (os dados ficam em .local-data/ e frontend/data/)
```

O container reinicia sozinho com o Docker (`restart: unless-stopped`). Cadencia: variavel `OFFLINE_INTERVAL_MINUTES` no `.env`.

## O que acontece quando a maquina fica desligada

Ao voltar, o servico executa uma vez cada tarefa que perdeu (uma coleta de cada produto, curadoria, publicacao). A curadoria verifica as ultimas 48 horas (`--catchup-hours`) e reconstroi o que faltar. Nao existe coleta retroativa: o plano Free so entrega dados atuais e previsoes, entao o periodo desligado fica sem observacoes.

## Consultas locais

```powershell
python scripts/query_local.py queries/monthly_from_daily.sql
python scripts/query_local.py queries/forecast_accuracy.sql --output erro_previsao.csv
python scripts/query_local.py --sql "SELECT state, max(temperature_max) FROM weather_daily_observations GROUP BY 1 ORDER BY 2 DESC"
```

As tabelas tem os mesmos nomes do Athena (`weather_hourly_observations`, `weather_daily_observations`, `weather_forecast_3h`). Os Parquet tambem abrem direto no Excel/Power BI (via conector Parquet), pandas, R ou DuckDB.

## Levar os dados da AWS para o offline

Antes de a conta do plano Free fechar (ou periodicamente, como backup):

```powershell
./scripts/export-from-aws.ps1 -StackName weather-data-pipeline-dev -Region sa-east-1            # tabelas curadas + dados do dashboard
./scripts/export-from-aws.ps1 -StackName weather-data-pipeline-dev -Region sa-east-1 -IncludeRaw  # inclui o raw dos ultimos 30 dias
```

Depois disso `start-offline.ps1` continua de onde a nuvem parou, no mesmo layout. O caminho inverso (subir dados locais para um stack novo) e um `aws s3 sync .local-data/lake/curated s3://<RawDataBucketName>/curated`.

## Backup

Tudo o que importa esta em duas pastas: `.local-data/lake/curated/` (historico consolidado) e `frontend/data/` (dados do dashboard, regeneraveis). Copie `.local-data/` para um disco externo ou pasta sincronizada (OneDrive, Google Drive) para ter backup.

## Espaco em disco

Com a cadencia padrao: ~1 GB por mes de raw (apagado apos 30 dias por padrao) e ~50 MB por mes de tabelas curadas.
