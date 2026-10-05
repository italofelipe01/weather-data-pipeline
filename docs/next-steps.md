# Proximas etapas

Ja implementado: Air Pollution, tabela horaria completa, previsoes curadas, agregados diarios por data local, catch-up automatico, teto mensal aplicado, alarmes com SNS, Glue/Athena com partition projection, dashboard web e CI/CD.

Possiveis evolucoes:

1. **Reduzir PUTs no S3**: agrupar os snapshots de um mesmo minuto em um unico objeto por produto (27 capitais por PUT) cortaria ~95% do principal custo do projeto.
2. **Precisao das previsoes no dashboard**: a consulta `queries/forecast_accuracy.sql` ja calcula vies e erro medio por antecedencia; publicar esse resultado em `data/` permitiria mostrar a confiabilidade da previsao por capital.
3. **Mapa**: camadas de mapa da OpenWeather (Basic weather maps, plano Free) exigem a chave no navegador; so fazem sentido com um proxy com cache.
4. **Alertas meteorologicos proprios**: regras simples (rajada acima de X, chuva acima de Y mm/h, AQI >= 4) publicadas no SNS.
5. **Testes de integracao com LocalStack**: `docker-compose.yml` e os scripts `start-local`/`stop-local` estao prontos, mas ainda nao ha testes marcados com `integration`.
6. **Arquivamento**: transicionar `curated/` para S3 Intelligent-Tiering quando o volume justificar (os arquivos atuais sao pequenos demais para compensar).
