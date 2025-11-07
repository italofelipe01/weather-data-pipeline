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
