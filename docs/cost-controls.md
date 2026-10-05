# Controle de custo e plano gratuito da AWS

## Resumo

| Cenario | Custo |
|---|---|
| Conta AWS no plano **Free** (6 meses, ate US$ 200 em creditos) | ~US$ 0,70/mes descontados dos creditos (~US$ 4 nos 6 meses). Nenhuma cobranca no cartao. |
| Conta AWS no plano **Paid** (depois dos 6 meses) | ~US$ 0,70/mes |
| **Modo offline** (sua maquina ou Docker) | US$ 0 de nuvem. So energia/internet da maquina. |

Com a cadencia padrao, so as requisicoes ao S3 saem dos creditos. Tudo o mais fica dentro das cotas **sempre gratuitas** da AWS.

## Como funciona o plano Free da AWS (contas criadas a partir de 15/07/2025)

- US$ 100 de creditos ao criar a conta, mais ate US$ 100 por atividades de onboarding.
- Vale por **6 meses** ou ate os creditos acabarem, o que vier primeiro. A conta nao e cobrada no cartao enquanto estiver no plano Free.
- **Ao final, a conta e fechada**: os recursos param, e voce tem 90 dias para migrar para o plano Paid e recuperar os dados; depois disso eles sao apagados.
- Servicos com cota "sempre gratuita" continuam gratuitos dentro do limite mensal (Lambda, SQS, CloudWatch, CloudFront, SNS, entre outros).

Por isso o projeto tem o **modo offline** e o script `export-from-aws.ps1`: antes de a conta fechar (ou a qualquer momento), copie os dados para sua maquina e continue coletando localmente. Veja [offline.md](offline.md).

## Estimativa mensal na AWS (sa-east-1, cadencia padrao, 31 dias)

| Servico | Volume aproximado | Cota sempre gratuita | Custo |
|---|---|---|---|
| Lambda | ~38 mil invocacoes, ~81 mil GB-s | 1 milhao de invocacoes, 400 mil GB-s | US$ 0 |
| SQS FIFO | ~50 mil mensagens + polling da Lambda (~0,7 milhao de requisicoes) | 1 milhao de requisicoes | US$ 0 |
| CloudWatch | ~50 MB de logs, 9 metricas, 9 alarmes, 1 dashboard | 5 GB, 10 metricas, 10 alarmes, 3 dashboards | US$ 0 |
| CloudFront | uso pessoal do dashboard | 1 TB e 10 milhoes de requisicoes | US$ 0 |
| SNS (e-mail) | poucos alertas | 1.000 e-mails | US$ 0 |
| SSM Parameter Store | 2 parametros padrao, ~35 mil chamadas | parametros padrao nao sao cobrados | US$ 0 |
| EventBridge (agendas) | 5 regras | regras agendadas nao sao cobradas | US$ 0 |
| Glue Data Catalog | 1 banco, 3 tabelas | 1 milhao de objetos/requisicoes | US$ 0 |
| Athena | so quando voce consulta (limite de 1 GB por consulta) | - | centavos por consulta |
| **S3** | ~62 mil PUT, ~16 mil LIST, ~165 mil GET, ~1 GB | sai dos creditos | **~US$ 0,68** |
| **Total** | | | **~US$ 0,70/mes** |

### O que foi feito para chegar aqui

- **Uma gravacao por coleta**, nao por capital: a Collector consulta as 27 capitais em sequencia e grava um unico objeto por snapshot. O raw caiu de ~445 mil para ~16,5 mil PUTs/mes, o que antes custava ~US$ 3,10/mes so de PUT.
- **Teto mensal sem CloudWatch GetMetricData**: o contador de chamadas fica num parametro SSM padrao (gratuito). A consulta de metricas do CloudWatch e cobrada por metrica consultada.
- **Collector com 128 MB**: a coleta espera a rede, nao usa CPU; o consumo fica em ~20% da cota gratuita de GB-s.
- **pyarrow so na Curator** (layer): pacotes menores e menos tempo de execucao.
- **Metricas e alarmes contados** para nao passar de 10 cada (cota do CloudWatch).
- Raw expira em 30 dias; resultados do Athena e `tmp/` em 7 dias; uploads incompletos em 1 dia; logs em 7 dias.
- Sem NAT Gateway, RDS, ECS, crawler do Glue ou servidores permanentes.

### Alavancas se quiser gastar ainda menos

| Ajuste | Efeito |
|---|---|
| `CurrentWeatherIntervalMinutes=5` | -40% de coletas da Current Weather |
| `EnableAirPollution=false` | -23 mil chamadas/mes a OpenWeather e -900 objetos/mes |
| `EnableAnalytics=false` | remove Glue/Athena (ja custam zero parados) |
| `EnableFrontend=false` | remove o CloudFront; o dashboard pode rodar no modo offline |
| Rodar no modo offline | zero de nuvem |

Se o plano Free bloquear algum servico na sua conta, desligue o recurso correspondente (`EnableAnalytics=false` para Glue/Athena, `EnableFrontend=false` para CloudFront) e faca o deploy de novo.

## Teto da OpenWeather

```text
1.000.000 chamadas/mes * 50% = 500.000 chamadas/mes (MonthlyOperationalCallLimit)
cadencia padrao: 445.284 chamadas em 31 dias
```

A Planner soma as chamadas que agenda num contador mensal (SSM na AWS, `.local-data/state/call-counter.json` no modo offline) e nao agenda coletas que ultrapassariam o teto. Quando isso acontece na AWS, emite `CollectionJobsSkipped` e o alarme `<stack>-monthly-call-limit` envia e-mail. O contador zera sozinho no dia 1.

Antes de habilitar a agenda, confirme no painel da OpenWeather que a conta esta no plano Free e que a chave ja esta ativa. O e-mail do Budget e o do SNS precisam ser confirmados quando a AWS enviar a inscricao.
