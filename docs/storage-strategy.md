# Estrategia de armazenamento

O objetivo e evitar que o S3 vire um deposito permanente de milhoes de JSONs pequenos e manter uma camada curada compacta e consultavel.

## Buckets e camadas

```text
<stack>-raw-<conta>-<regiao>
  raw/             snapshots brutos da OpenWeather            expira em RawDataRetentionDays (30)
  curated/         tabelas Parquet (Snappy)                   longo prazo
  athena-results/  resultados do workgroup                    expira em 7 dias
  tmp/, rejected/  reservados                                 expiram

<stack>-sitebucket-*
  index.html, assets/   dashboard (publish-frontend.ps1)
  data/                 JSON do dashboard (Curator e Publisher)
```

## Chaves

```text
raw/source=openweather-free-plan/product=<produto>/year=<yyyy>/month=<mm>/day=<dd>/hour=<hh>/state=<uf>/city=<cidade>/openweather_<produto>_<uf>_<cidade>_<yyyymmddThhmmZ>.json
curated/hourly_observations/year=<yyyy>/month=<mm>/day=<dd>/hour=<hh>/weather_hourly_observations_<yyyymmddThh00Z>.parquet
curated/daily_observations/year=<yyyy>/month=<mm>/day=<dd>/weather_daily_observations_<yyyymmdd>.parquet
curated/forecast_3h/year=<yyyy>/month=<mm>/day=<dd>/hour=<hh>/weather_forecast_3h_<yyyymmddThh00Z>.parquet
```

- Horaria: um arquivo por hora UTC com todas as capitais (clima + qualidade do ar).
- Diaria: um arquivo por **data local**, todas as capitais.
- Previsao: um arquivo por hora de emissao, com as 40 previsoes de cada capital.

As particoes `year/month/day/hour` sao lidas pelo Athena via partition projection (nao ha crawler). As tabelas tambem trazem `year`, `month` e `day` como colunas para facilitar leitura fora do Athena.

## Por que expirar o raw

Com a cadencia padrao o pipeline grava cerca de 445 mil objetos por mes. O raw so e necessario para reprocessamento (`invoke-curator.ps1 -StartHour/-EndHour`), entao 30 dias bastam. A camada curada guarda ~720 arquivos horarios, ~720 de previsao e ~30 diarios por mes.

## Compatibilidade

Arquivos horarios gravados pela primeira versao (com `rain_1h_sum` somado por snapshot e sem data local) sao normalizados na leitura (`normalize_hourly_record`): `rain_mm = rain_1h_sum / sample_count` e a data local e calculada pelo fuso da capital. Para regrava-los no formato novo, reprocesse as horas com o raw ainda disponivel.

## JSON do dashboard

| Documento | Escrito por | Atualizacao | Conteudo |
|---|---|---|---|
| `data/latest.json` | Publisher | 10 min | observacao e qualidade do ar mais recentes das 27 capitais, consumo do mes |
| `data/hourly/<uf>.json` | Curator | 1 h | 7 dias de linhas horarias |
| `data/daily/<uf>.json` | Curator | quando um dia fecha | ate 730 dias (merge incremental; `rebuild_serving` refaz) |
| `data/forecast/<uf>.json` | Curator | 1 h | previsao de 5 dias e de qualidade do ar de 4 dias |

Capitais sem dado novo mantem o ultimo valor publicado, entao uma falha pontual nao apaga o dashboard.
