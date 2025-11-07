# 🚀 Quick Start Guide - Weather Data Pipeline

## 📋 Pré-requisitos

- Docker 20.10+ instalado
- Docker Compose 2.0+ instalado
- 8GB RAM disponível
- 20GB espaço em disco
- Conta gratuita OpenWeatherMap API

---

## 🎯 Instalação em 5 Minutos

### Passo 1: Clonar ou criar o projeto

```bash
mkdir weather-pipeline
cd weather-pipeline
```

### Passo 2: Obter API Key do OpenWeatherMap

1. Acesse: https://openweathermap.org/api
2. Crie uma conta gratuita
3. Vá em "API Keys" e copie sua chave
4. Guarde para usar no passo 4

### Passo 3: Criar estrutura de arquivos

Crie os seguintes arquivos na raiz do projeto:

1. **docker-compose.yml** (use o arquivo fornecido anteriormente)
2. **.env.example** (use o arquivo fornecido)
3. **requirements.txt** (use o arquivo fornecido)
4. **database/init_scripts/01_create_schemas.sql** (use o script fornecido)

### Passo 4: Configurar variáveis de ambiente

```bash
# Copiar exemplo
cp .env.example .env

# Editar .env
nano .env  # ou use seu editor preferido
```

**Configurações OBRIGATÓRIAS no .env:**

```bash
# Sua API Key do OpenWeatherMap
OPENWEATHER_API_KEY=SUA_CHAVE_AQUI

# Senha forte para o PostgreSQL
POSTGRES_PASSWORD=minha_senha_forte_123

# Gerar Fernet Key (execute no terminal):
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Cole o resultado em:
AIRFLOW__CORE__FERNET_KEY=resultado_aqui

# Gerar Superset Secret (execute no terminal):
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Cole o resultado em:
SUPERSET_SECRET_KEY=resultado_aqui
```

### Passo 5: Executar script de setup

```bash
# Dar permissão de execução
chmod +x setup.sh

# Executar setup
./setup.sh
```

Ou manualmente:

```bash
# Criar diretórios
mkdir -p airflow/{dags,logs,plugins,config}
mkdir -p database/init_scripts
mkdir -p dbt_project extractors notebooks

# Configurar UID do Airflow
echo "AIRFLOW_UID=$(id -u)" >> .env

# Baixar imagens
docker-compose pull

# Iniciar serviços
docker-compose up -d

# Aguardar inicialização (2-3 minutos)
sleep 120
```

### Passo 6: Verificar serviços

```bash
# Ver status
docker-compose ps

# Todos devem estar "healthy" ou "running"
```

### Passo 7: Acessar interfaces

**Airflow:**
- URL: http://localhost:8080
- User: `admin`
- Password: `admin`

**Superset:**
- URL: http://localhost:8088
- User: `admin`
- Password: `admin`

**pgAdmin (opcional):**
- URL: http://localhost:5050
- Email: `admin@admin.com`
- Password: `admin`

---

## 🔧 Configuração Inicial

### 1. Configurar Airflow

#### 1.1 Adicionar Conexão PostgreSQL

1. Acesse Airflow: http://localhost:8080
2. Vá em: **Admin → Connections**
3. Clique em **+** (Add)
4. Preencha:
   - **Connection Id**: `postgres_weather`
   - **Connection Type**: `Postgres`
   - **Host**: `postgres`
   - **Schema**: `weather_db`
   - **Login**: `postgres`
   - **Password**: (sua senha do .env)
   - **Port**: `5432`
5. Clique **Save**

#### 1.2 Adicionar Variáveis

1. Vá em: **Admin → Variables**
2. Adicione:

| Key | Value |
|-----|-------|
| `OPENWEATHER_API_KEY` | Sua API key |
| `CITIES_LIST` | `["São Paulo", "London", "New York"]` |

### 2. Verificar Database

```bash
# Conectar ao PostgreSQL
docker-compose exec postgres psql -U postgres -d weather_db

# Verificar schemas
\dn

# Deve mostrar: raw, staging, analytics, metadata

# Verificar tabelas
\dt raw.*

# Sair
\q
```

---

## 🎬 Primeira Execução

### 1. Trigger Manual de Extração

1. No Airflow, vá para **DAGs**
2. Procure por `weather_extraction`
3. Ative a DAG (toggle ON)
4. Clique no play ▶️ → **Trigger DAG**
5. Clique no nome da DAG para ver execução
6. Aguarde todas as tasks ficarem verde ✅

### 2. Verificar Dados Extraídos

```bash
# Conectar ao banco
docker-compose exec postgres psql -U postgres -d weather_db

# Ver dados extraídos
SELECT 
    city_name, 
    temperature_celsius, 
    humidity_percent,
    weather_main,
    timestamp_utc 
FROM raw.weather_current 
ORDER BY timestamp_utc DESC 
LIMIT 5;

# Contar registros
SELECT COUNT(*) FROM raw.weather_current;
```

### 3. Executar Transformação dbt (manual)

```bash
# Entrar no container do Airflow
docker-compose exec airflow-worker bash

# Navegar para dbt
cd /opt/airflow/dbt_project

# Instalar dependências (primeira vez)
dbt deps

# Executar modelos
dbt run

# Executar testes
dbt test

# Sair
exit
```

---

## 📊 Configurar Superset

### 1. Adicionar Database

1. Acesse: http://localhost:8088
2. Login: admin/admin
3. Vá em: **Settings → Database Connections**
4. Clique **+ Database**
5. Selecione **PostgreSQL**
6. Preencha:
   ```
   Host: postgres
   Port: 5432
   Database: weather_db
   Username: postgres
   Password: (sua senha)
   ```
7. **Test Connection** → **Connect**

### 2. Criar Primeiro Dataset

1. Vá em: **Data → Datasets**
2. Clique **+ Dataset**
3. Selecione:
   - **Database**: PostgreSQL (o que você criou)
   - **Schema**: `analytics`
   - **Table**: `fato_clima_diario` (se já tiver executado dbt)
4. **Add**

### 3. Criar Primeiro Chart

1. No dataset criado, clique **Create Chart**
2. Escolha: **Line Chart**
3. Configure:
   - **X-Axis**: `date`
   - **Metrics**: `AVG(temp_media)`
   - **Group by**: `city_name`
   - **Filters**: Últimos 30 dias
4. **Create Chart**
5. **Save**

---

## ⚙️ Comandos Úteis

### Docker Compose

```bash
# Ver logs de todos os serviços
docker-compose logs -f

# Ver logs de um serviço específico
docker-compose logs -f airflow-scheduler

# Parar todos os serviços
docker-compose down

# Parar e remover volumes (CUIDADO: apaga dados)
docker-compose down -v

# Reiniciar um serviço
docker-compose restart airflow-webserver

# Ver status
docker-compose ps

# Ver uso de recursos
docker stats
```

### Entrar nos Containers

```bash
# Airflow
docker-compose exec airflow-webserver bash

# PostgreSQL
docker-compose exec postgres psql -U postgres -d weather_db

# Superset
docker-compose exec superset bash
```

### Backup

```bash
# Backup do banco
docker-compose exec postgres pg_dump -U postgres weather_db > backup.sql

# Restaurar
cat backup.sql | docker-compose exec -T postgres psql -U postgres -d weather_db
```

---

## 🐛 Troubleshooting

### Problema: Airflow não inicia

```bash
# Ver logs
docker-compose logs airflow-webserver

# Reiniciar
docker-compose restart airflow-webserver airflow-scheduler

# Re-inicializar banco do Airflow
docker-compose exec airflow-webserver airflow db reset
```

### Problema: PostgreSQL não conecta

```bash
# Verificar se está rodando
docker-compose ps postgres

# Testar conexão
docker-compose exec postgres pg_isready -U postgres

# Ver logs
docker-compose logs postgres
```

### Problema: Erro de permissão

```bash
# Ajustar permissões
sudo chown -R $USER:$USER airflow/

# Ou configurar UID correto
echo "AIRFLOW_UID=$(id -u)" >> .env
docker-compose down
docker-compose up -d
```

### Problema: Porta já em uso

```bash
# Ver o que está usando a porta 8080
lsof -i :8080

# Matar processo ou mudar porta no docker-compose.yml
# Trocar "8080:8080" por "8081:8080"
```

### Problema: Falta de memória

```bash
# Verificar uso
docker stats

# Aumentar memória do Docker Desktop
# Settings → Resources → Memory → 8GB

# Ou reduzir workers do Airflow
# Editar docker-compose.yml, comentar airflow-worker
```

---

## 📚 Próximos Passos

### 1. Adicionar Mais Cidades

Edite o arquivo `dbt_project/seeds/cidades.csv`:

```csv
city_name,country_code,country_name,region,timezone,population
Curitiba,BR,Brasil,Sul,America/Sao_Paulo,1900000
```

Execute:
```bash
docker-compose exec airflow-worker bash
cd /opt/airflow/dbt_project
dbt seed
```

### 2. Criar DAGs Customizadas

Crie arquivo em `airflow/dags/minha_dag.py`

### 3. Criar Modelos dbt

Crie arquivo em `dbt_project/models/marts/meu_modelo.sql`

### 4. Agendar Execuções

No Airflow, configure o schedule_interval da DAG

---

## 📖 Documentação Adicional

- [Documentação OpenWeatherMap](https://openweathermap.org/api)
- [Apache Airflow Docs](https://airflow.apache.org/docs/)
- [dbt Docs](https://docs.getdbt.com/)
- [Apache Superset](https://superset.apache.org/)
- [PostgreSQL](https://www.postgresql.org/docs/)

---

## 🆘 Suporte

- GitHub Issues: [seu-repo]/issues
- Email: seu-email@example.com

---

## ✅ Checklist de Verificação

- [ ] Docker e Docker Compose instalados
- [ ] API Key do OpenWeatherMap obtida
- [ ] Arquivo .env configurado corretamente
- [ ] Todos os containers iniciados (docker-compose ps)
- [ ] Airflow acessível em localhost:8080
- [ ] Superset acessível em localhost:8088
- [ ] PostgreSQL aceitando conexões
- [ ] Primeira extração executada com sucesso
- [ ] Dados visíveis no banco
- [ ] dbt models executados
- [ ] Primeiro chart criado no Superset

---

**🎉 Parabéns! Seu pipeline está funcionando!**