# Decisoes tecnicas

## Lambda em vez de Airflow

Lambda atende melhor a uma coleta orientada a eventos, com baixo custo quando o pipeline esta parado. Airflow seria mais pesado para esta etapa.

## SQS FIFO

SQS desacopla planejamento e coleta. FIFO foi usado para deduplicar trabalhos iguais e manter ordenacao por UF.

## Current Weather e Forecast em vez de historico pago

O projeto usa o plano gratuito da OpenWeather para formar historico proprio a partir de snapshots recorrentes. Isso evita depender de One Call, History API ou outro produto historico pago nesta etapa.

## Teto operacional de 50%

Embora o plano gratuito documente 1.000.000 chamadas por mes para current weather e forecasts, o projeto usa 500.000 chamadas por mes como limite operacional. A cadencia padrao estimada consome aproximadamente 408.240 chamadas por mes.

## S3 como raw zone

O S3 e o destino correto para a primeira camada de dados: barato, duravel e adequado para Glue/Athena na etapa seguinte.

## SSM Parameter Store

A chave OpenWeather fica em SecureString no SSM. Secrets Manager nao foi usado para evitar custo adicional e porque a rotacao automatica nao e requisito desta etapa.

## Sem DynamoDB

A idempotencia inicial e resolvida por deduplicacao da SQS FIFO e chave deterministica no S3 com `If-None-Match`.

## Sem Glue e Athena nesta etapa

O pedido atual prioriza corrigir e implementar ate a fonte de dados regularizada. Glue/Athena devem ser adicionados quando houver amostra raw validada.
