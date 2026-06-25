# Controle de custo

O projeto usa 50% do teto mensal gratuito documentado para current weather e forecasts:

```text
1.000.000 chamadas/mes * 50% = 500.000 chamadas/mes
```

Cadencia padrao estimada:

```text
current weather: 388.800 chamadas/mes
forecast 5d/3h: 19.440 chamadas/mes
total estimado: 408.240 chamadas/mes
```

Medidas de controle:

- EventBridge desabilitado por padrao.
- SQS desacopla chamadas e evita disparos diretos em massa.
- Nao usar Geocoding a cada execucao.
- Nao usar APIs historicas pagas.
- Logs com retencao padrao de 7 dias.
- Lifecycle no S3 com `raw/` expirando em 30 dias por padrao.
- Budget opcional no CloudFormation quando `BudgetAlertEmail` e informado.
- Sem NAT Gateway, RDS, ECS, MSK ou servidores permanentes.

Antes de habilitar agenda, confirme no painel da OpenWeather se a conta esta no plano gratuito correto e se existem alertas de uso configurados.

## Operacao com US$ 100 de credito

Comece com `EnableSchedules=false`, execute coletas manuais por alguns dias e valide o volume no S3 e no CloudWatch. Depois habilite agenda com budget mensal baixo, por exemplo US$ 10.

Exemplo:

```powershell
./scripts/deploy.ps1 `
  -StackName weather-data-pipeline-dev `
  -Environment dev `
  -Region sa-east-1 `
  -MonthlyBudgetAmount 10 `
  -BudgetAlertEmail "seu-email@example.com" `
  -EnableSchedules true
```

O e-mail de budget precisa ser confirmado quando a AWS enviar a inscricao.
