# Dicionario de dados

Unidades: temperatura em C, pressao em hPa, vento em m/s (o dashboard mostra km/h), visibilidade em metros, precipitacao em mm, poluentes em ug/m3. Timestamps em UTC (`timestamp` sem fuso no Parquet). Os schemas ficam em `src/shared/*_table.py` e o teste `tests/unit/test_template.py` garante que as tabelas do Glue batem com eles.

## `weather_hourly_observations`

Uma linha por capital por hora UTC. Particoes: `year`, `month`, `day`, `hour`.

| Coluna | Descricao |
|---|---|
| `observation_date`, `observation_hour`, `observation_timestamp` | inicio da hora UTC |
| `local_date`, `local_hour` | data e hora local da capital |
| `city`, `state`, `region`, `ibge_code`, `latitude`, `longitude` | identificacao da capital |
| `temperature_avg/min/max` | media e extremos das observacoes distintas da hora |
| `feels_like_avg` | sensacao termica media |
| `humidity_avg/min/max` | umidade relativa (%) |
| `pressure_avg`, `sea_level_pressure_avg`, `ground_level_pressure_avg` | pressao |
| `wind_speed_avg/max`, `wind_gust_max`, `wind_deg_avg` | vento; direcao e media circular (graus de onde vem) |
| `clouds_avg`, `visibility_avg` | nebulosidade (%) e visibilidade (m) |
| `rain_mm`, `rain_rate_max`, `snow_mm` | precipitacao estimada na hora (media de mm/h) e intensidade maxima |
| `weather_id/main/description/icon` | condicao predominante (moda) |
| `sunrise`, `sunset` | nascer e por do sol |
| `aqi` | indice de qualidade do ar 1-5 (maior valor da hora) |
| `co`, `no`, `no2`, `o3`, `so2`, `pm2_5`, `pm10`, `nh3` | concentracoes |
| `sample_count` | snapshots de Current Weather gravados na hora |
| `observation_count` | observacoes distintas (`dt`) usadas nas medias |
| `air_sample_count` | snapshots de Air Pollution na hora |
| `source_product`, `processed_at` | origem e horario do processamento |

## `weather_daily_observations`

Uma linha por capital por data local. Particoes: `year`, `month`, `day` da data local.

| Coluna | Descricao |
|---|---|
| `observation_date` | data local |
| `temperature_avg/min/max`, `temperature_amplitude` | media das horas, extremos absolutos e amplitude |
| `feels_like_avg/max` | sensacao termica |
| `humidity_avg/min/max`, `pressure_avg` | umidade e pressao |
| `wind_speed_avg/max`, `wind_gust_max`, `clouds_avg`, `visibility_avg` | vento, nuvens, visibilidade |
| `rain_mm`, `rain_hours`, `snow_mm` | chuva acumulada no dia e horas com chuva |
| `weather_main/description/icon` | condicao predominante das horas diurnas |
| `sunrise`, `sunset` | nascer e por do sol |
| `aqi_avg`, `aqi_max`, `pm2_5_avg`, `pm10_avg`, `o3_avg`, `no2_avg`, `so2_avg`, `co_avg` | qualidade do ar |
| `hours_observed`, `sample_count` | cobertura do dia (24 = completo) |

## `weather_forecast_3h`

Uma linha por capital por horario previsto, para cada hora de emissao. Particoes: `year`, `month`, `day`, `hour` da emissao.

| Coluna | Descricao |
|---|---|
| `issued_at`, `forecast_time`, `lead_hours` | emissao, horario previsto e antecedencia em horas |
| `forecast_date`, `forecast_hour`, `local_forecast_date`, `local_forecast_hour` | horario previsto em UTC e local |
| `temperature`, `feels_like`, `temperature_min/max`, `humidity`, `pressure`, `sea_level_pressure`, `ground_level_pressure` | condicoes previstas |
| `clouds`, `wind_speed`, `wind_deg`, `wind_gust`, `visibility` | nuvens, vento, visibilidade |
| `pop` | probabilidade de precipitacao (0-1) |
| `rain_3h_mm`, `snow_3h_mm` | volume previsto nas 3 horas anteriores a `forecast_time` |
| `weather_id/main/description/icon`, `part_of_day` | condicao prevista; `d` dia, `n` noite |
| `city_population` | populacao informada pela OpenWeather |
