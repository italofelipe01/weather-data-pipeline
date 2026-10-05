# Dashboard

Site estatico em `frontend/`, sem build e sem dependencias de terceiros (HTML, CSS e modulos ES). E servido pelo CloudFront a partir do bucket do site e le os documentos JSON em `data/`.

## Paginas

| Rota | Conteudo |
|---|---|
| `#/` | destaques (mais quente, mais fria, menor umidade, pior ar, chovendo agora), ranking por metrica com filtro de regiao, resumo por regiao e cards das 27 capitais |
| `#/capital/<UF>` | condicoes atuais com todos os campos da Current Weather, qualidade do ar vs diretrizes OMS 2021, previsao de 5 dias (temperatura, sensacao, chuva e probabilidade), previsao de qualidade do ar de 4 dias, ultimas 24 h / 72 h / 7 dias e historico por dia, semana, mes ou ano (30 dias a 2 anos) |
| `#/comparar?ufs=SP,RJ&metrica=temperature&periodo=7d` | ate 4 capitais na mesma escala; as cores ficam presas a cada capital |
| `#/sobre` | situacao do pipeline, consumo mensal da OpenWeather, APIs usadas e como ler os numeros |

Os filtros ficam na URL, entao qualquer visao pode ser compartilhada.

## Acessibilidade e design

- Tema claro/escuro (automatico ou escolhido, lembrado no navegador).
- Graficos SVG com crosshair e tooltip por mouse e teclado (setas, Home, End), legenda para mais de uma serie e tabela equivalente ("Ver dados em tabela") para todos os graficos.
- Paleta categorica validada para daltonismo; qualidade do ar usa cores de status sempre acompanhadas de icone e rotulo.
- Layout responsivo ate 360 px de largura, sem rolagem horizontal.
- Aviso automatico quando os dados tem mais de 45 minutos; o painel se atualiza sozinho a cada 5 minutos.

## Contrato de dados

Todos os documentos tem `schema_version` e `generated_at`. Os nomes de campos seguem `src/shared/serving.py`:

- `latest.json`: `capitals[]` com `state`, `name`, `region`, `timezone`, `utc_offset_seconds`, `current` (observacao) e `air` (qualidade do ar); `budget` com o consumo do mes.
- `hourly/<uf>.json`, `daily/<uf>.json`: `capital` e `rows[]` com as colunas das tabelas curadas.
- `forecast/<uf>.json`: `weather.items[]` (3 h) e `air.items[]` (1 h).

## Desenvolvimento local

```powershell
./scripts/preview-frontend.ps1                    # dados sinteticos
./scripts/run-local-pipeline.ps1 -States SP -Serve  # API real
```

Os icones de condicao vem de `openweathermap.org/img/wn/` (sem chave). A Content Security Policy do CloudFront libera apenas esse dominio para imagens.
