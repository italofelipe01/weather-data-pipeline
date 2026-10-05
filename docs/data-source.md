# Fonte de dados

Fonte: OpenWeather, somente produtos incluidos no plano **Free** (60 chamadas/minuto e 1.000.000 chamadas/mes).

| Produto | Endpoint | Parametros | Uso no projeto |
|---|---|---|---|
| Current Weather | `https://api.openweathermap.org/data/2.5/weather` | `lat`, `lon`, `units=metric`, `lang=pt_br` | observacao atual |
| 5 Day / 3 Hour Forecast | `https://api.openweathermap.org/data/2.5/forecast` | `lat`, `lon`, `units=metric`, `lang=pt_br` | 40 previsoes de 3 h |
| Air Pollution | `https://api.openweathermap.org/data/2.5/air_pollution` | `lat`, `lon` | qualidade do ar atual |
| Air Pollution forecast | `https://api.openweathermap.org/data/2.5/air_pollution/forecast` | `lat`, `lon` | previsao horaria de 4 dias |

Nao usamos One Call, History API, Air Pollution history nem qualquer produto pago. Geocoding nao e chamado: as coordenadas das capitais ficam versionadas em `src/shared/capitals.py`.

## Campos aproveitados

**Current Weather**: `main.temp`, `feels_like`, `temp_min`, `temp_max`, `humidity`, `pressure`, `sea_level`, `grnd_level`; `visibility`; `wind.speed`, `deg`, `gust`; `clouds.all`; `rain.1h`, `snow.1h`; `weather[0].id/main/description/icon`; `sys.sunrise/sunset`; `dt` (horario da observacao); `name`.

**Forecast**: por item `dt`, `main.*`, `weather[0].*`, `clouds.all`, `wind.*`, `visibility`, `pop` (probabilidade de precipitacao), `rain.3h`, `snow.3h`, `sys.pod`; da cidade `population`, `sunrise`, `sunset`.

**Air Pollution**: `main.aqi` (1 = boa ... 5 = muito ruim) e `components` em ug/m3: `co`, `no`, `no2`, `o3`, `so2`, `pm2_5`, `pm10`, `nh3`.

## Semantica que afeta as agregacoes

- `rain.1h` e `snow.1h` sao **intensidade em mm/h** (ausencia = sem precipitacao). A chuva de uma hora e a media das intensidades observadas na hora; somar os ~20 snapshots da hora contaria a mesma chuva ~20 vezes.
- A Current Weather e recalculada pela OpenWeather a cada ~10 minutos. Com coleta a cada 3 minutos, varios snapshots trazem o mesmo `dt`; a tabela horaria considera cada observacao distinta uma unica vez (`observation_count`), e `sample_count` registra quantos snapshots foram gravados.
- `main.temp_min/temp_max` da Current Weather indicam variacao espacial no momento, nao minima/maxima do dia. As colunas `temperature_min/max` das tabelas sao extremos **temporais** das observacoes.
- `rain.3h` da previsao e o volume esperado nas 3 horas anteriores ao `dt`.

## Limites e ritmo

- Teto adotado: 500.000 chamadas/mes (50% do Free), aplicado pela Planner.
- Cadencia padrao: 445.284 chamadas em 31 dias (detalhe no README).
- Cada agenda gera 27 chamadas; no maximo duas agendas compartilham uma janela de 60 s, e a Collector roda com concorrencia maxima 2.
- HTTP 429, 5xx, 408, 425 e timeouts sao reprocessados pela fila. HTTP 401 descarta a chave em cache e tambem e reprocessado (uma chave nova pode levar algumas horas para ser ativada pela OpenWeather). 400/403/404 e respostas fora do formato sao descartados e contados em `SourceJobsRejected`.
