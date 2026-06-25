#!/bin/bash

# ==========================================
# WEATHER DATA PIPELINE - SETUP SCRIPT
# ==========================================

set -e  # Exit on error

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções auxiliares
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

# ==========================================
# VERIFICAÇÕES INICIAIS
# ==========================================

print_header "VERIFICANDO PRÉ-REQUISITOS"

# Verificar Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker não está instalado!"
    exit 1
fi
print_success "Docker instalado"

# Verificar Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose não está instalado!"
    exit 1
fi
print_success "Docker Compose instalado"

# Verificar se Docker está rodando
if ! docker info &> /dev/null; then
    print_error "Docker não está rodando!"
    exit 1
fi
print_success "Docker está rodando"

# ==========================================
# CRIAR ESTRUTURA DE DIRETÓRIOS
# ==========================================

print_header "CRIANDO ESTRUTURA DE DIRETÓRIOS"

directories=(
    "airflow/dags"
    "airflow/logs"
    "airflow/plugins"
    "airflow/config"
    "database/init_scripts"
    "extractors/utils"
    "dbt_project/models/staging"
    "dbt_project/models/intermediate"
    "dbt_project/models/marts"
    "dbt_project/tests"
    "dbt_project/macros"
    "dbt_project/seeds"
    "great_expectations/expectations"
    "great_expectations/checkpoints"
    "superset/dashboards"
    "notebooks"
    "tests/unit"
    "tests/integration"
    "docs"
    "backups"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
    print_success "Criado: $dir"
done

# ==========================================
# CONFIGURAR VARIÁVEIS DE AMBIENTE
# ==========================================

print_header "CONFIGURANDO VARIÁVEIS DE AMBIENTE"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        print_success "Arquivo .env criado a partir do .env.example"
        print_warning "IMPORTANTE: Edite o arquivo .env com suas credenciais!"
        print_info "Você precisa configurar:"
        print_info "  - OPENWEATHER_API_KEY"
        print_info "  - POSTGRES_PASSWORD"
        print_info "  - SUPERSET_SECRET_KEY"
        print_info "  - AIRFLOW__CORE__FERNET_KEY"
        echo ""
        read -p "Pressione ENTER para continuar depois de editar o .env..."
    else
        print_error ".env.example não encontrado!"
        exit 1
    fi
else
    print_info "Arquivo .env já existe"
fi

# Gerar secrets se necessário
print_info "Gerando secrets..."

# Fernet Key para Airflow
if ! grep -q "AIRFLOW__CORE__FERNET_KEY=your_fernet_key_here" .env; then
    print_info "Fernet Key já configurada"
else
    print_warning "Gerando Fernet Key..."
    FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "GENERATE_MANUALLY")
    if [ "$FERNET_KEY" != "GENERATE_MANUALLY" ]; then
        sed -i "s/AIRFLOW__CORE__FERNET_KEY=your_fernet_key_here/AIRFLOW__CORE__FERNET_KEY=$FERNET_KEY/" .env
        print_success "Fernet Key gerada"
    else
        print_warning "Execute: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    fi
fi

# Secret Key para Superset
if ! grep -q "SUPERSET_SECRET_KEY=your_superset_secret_key_here" .env; then
    print_info "Superset Secret Key já configurada"
else
    print_warning "Gerando Superset Secret Key..."
    SUPERSET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || echo "GENERATE_MANUALLY")
    if [ "$SUPERSET_KEY" != "GENERATE_MANUALLY" ]; then
        sed -i "s/SUPERSET_SECRET_KEY=your_superset_secret_key_here/SUPERSET_SECRET_KEY=$SUPERSET_KEY/" .env
        print_success "Superset Secret Key gerada"
    else
        print_warning "Execute: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    fi
fi

# Configurar AIRFLOW_UID
echo -e "\nAIRFLOW_UID=$(id -u)" >> .env
print_success "AIRFLOW_UID configurado"

# ==========================================
# CRIAR ARQUIVOS NECESSÁRIOS
# ==========================================

print_header "CRIANDO ARQUIVOS DE CONFIGURAÇÃO"

# .gitignore
if [ ! -f .gitignore ]; then
    cat > .gitignore << 'EOF'
# Environment
.env
*.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/

# Airflow
airflow/logs/*
!airflow/logs/.gitkeep
airflow/*.pid
airflow/airflow.db
airflow/airflow.cfg

# dbt
dbt_project/target/
dbt_project/dbt_packages/
dbt_project/logs/

# Great Expectations
great_expectations/uncommitted/

# Jupyter
.ipynb_checkpoints/
notebooks/.ipynb_checkpoints/

# Docker
postgres_data/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Backups
backups/*.sql
backups/*.sql.gz

# Logs
*.log
EOF
    print_success "Criado .gitignore"
fi

# README.md
if [ ! -f README.md ]; then
    cat > README.md << 'EOF'
# Weather Data Pipeline

Pipeline end-to-end de dados de clima usando ferramentas open-source.

## Stack Tecnológico

- **Source**: OpenWeatherMap API
- **Extraction**: Python + Requests
- **Storage**: PostgreSQL
- **Transformation**: dbt Core
- **Orchestration**: Apache Airflow
- **Quality**: Great Expectations
- **BI**: Apache Superset
- **Containerization**: Docker + Docker Compose

## Quick Start

1. Configure o arquivo `.env` com suas credenciais
2. Execute: `./setup.sh`
3. Inicie os serviços: `docker-compose up -d`
4. Acesse:
   - Airflow: http://localhost:8080 (admin/admin)
   - Superset: http://localhost:8088 (admin/admin)
   - pgAdmin: http://localhost:5050 (admin@admin.com/admin)

## Documentação

Veja a pasta `docs/` para documentação completa.
EOF
    print_success "Criado README.md"
fi

# ==========================================
# BAIXAR IMAGENS DOCKER
# ==========================================

print_header "BAIXANDO IMAGENS DOCKER"

print_info "Isso pode levar alguns minutos..."

docker-compose pull

print_success "Imagens baixadas"

# ==========================================
# CONSTRUIR CONTAINERS CUSTOMIZADOS
# ==========================================

print_header "CONSTRUINDO CONTAINERS"

docker-compose build --no-cache

print_success "Containers construídos"

# ==========================================
# INICIALIZAR SERVIÇOS
# ==========================================

print_header "INICIALIZANDO SERVIÇOS"

print_info "Iniciando containers..."
docker-compose up -d

print_info "Aguardando serviços ficarem prontos (60 segundos)..."
sleep 60

# Verificar status
print_info "Verificando status dos serviços..."
docker-compose ps

# ==========================================
# VERIFICAR SAÚDE DOS SERVIÇOS
# ==========================================

print_header "VERIFICANDO SAÚDE DOS SERVIÇOS"

# PostgreSQL
print_info "Testando PostgreSQL..."
if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    print_success "PostgreSQL está saudável"
else
    print_error "PostgreSQL não está respondendo"
fi

# Airflow
print_info "Testando Airflow..."
if curl -s http://localhost:8080/health | grep -q "healthy" 2>/dev/null; then
    print_success "Airflow está saudável"
else
    print_warning "Airflow ainda está inicializando (pode levar mais tempo)"
fi

# Superset
print_info "Testando Superset..."
if curl -s http://localhost:8088/health > /dev/null 2>&1; then
    print_success "Superset está saudável"
else
    print_warning "Superset ainda está inicializando"
fi

# ==========================================
# RESUMO FINAL
# ==========================================

print_header "INSTALAÇÃO CONCLUÍDA"

echo -e "${GREEN}✓ Projeto configurado com sucesso!${NC}\n"

echo -e "${BLUE}Acessos:${NC}"
echo -e "  • Airflow:  ${YELLOW}http://localhost:8080${NC}  (admin/admin)"
echo -e "  • Superset: ${YELLOW}http://localhost:8088${NC}  (admin/admin)"
echo -e "  • pgAdmin:  ${YELLOW}http://localhost:5050${NC}  (admin@admin.com/admin)"
echo -e ""

echo -e "${BLUE}Comandos úteis:${NC}"
echo -e "  • Ver logs:          ${YELLOW}docker-compose logs -f${NC}"
echo -e "  • Parar serviços:    ${YELLOW}docker-compose down${NC}"
echo -e "  • Reiniciar:         ${YELLOW}docker-compose restart${NC}"
echo -e "  • Status:            ${YELLOW}docker-compose ps${NC}"
echo -e "  • Entrar no Airflow: ${YELLOW}docker-compose exec airflow-webserver bash${NC}"
echo -e ""

echo -e "${BLUE}Próximos passos:${NC}"
echo -e "  1. Configure sua API Key no Airflow (Admin → Variables)"
echo -e "  2. Ative as DAGs no Airflow UI"
echo -e "  3. Trigger manual da DAG 'weather_extraction'"
echo -e "  4. Configure o Superset com a conexão ao PostgreSQL"
echo -e ""

print_warning "IMPORTANTE: Não esqueça de configurar o OPENWEATHER_API_KEY no arquivo .env!"

echo ""