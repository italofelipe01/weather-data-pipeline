# Fonte de dados

Fonte selecionada: OpenWeather, usando apenas produtos indicados no plano gratuito de current weather e forecasts.

Endpoints:

```text
https://api.openweathermap.org/data/2.5/weather
https://api.openweathermap.org/data/2.5/forecast
```

Limites operacionais:

- Limite documentado do plano gratuito: 60 chamadas/minuto e 1.000.000 chamadas/mes.
- Limite adotado no projeto: 500.000 chamadas/mes, equivalente a 50% do teto mensal.
- Cadencia padrao: current weather a cada 3 minutos e forecast a cada 1 hora para 27 capitais.

Justificativa:

- Evita dependencia de produto historico pago.
- Cria historico proprio a partir da data de inicio da coleta.
- Mantem custo previsivel.
- Permite agregacoes horarias, diarias, semanais e mensais quando houver dados acumulados.

Nao usamos Geocoding em runtime porque as coordenadas das capitais ficam versionadas no codigo.
