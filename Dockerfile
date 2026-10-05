# Offline mode: the whole pipeline (collection, curation, dashboard) in one container, no AWS needed.
#   docker compose up -d        ->  http://localhost:8000
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements-offline.txt .
RUN pip install -r requirements-offline.txt && mkdir -p /app/.local-data /app/frontend/data

COPY src ./src
COPY scripts ./scripts
COPY frontend ./frontend
COPY queries ./queries

# Runs as root so the bind-mounted data folders are writable on Linux and Docker Desktop alike;
# the container only makes outbound HTTPS calls and serves static files.
EXPOSE 8000
VOLUME ["/app/.local-data", "/app/frontend/data"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"
CMD ["python", "scripts/offline_service.py", "--host", "0.0.0.0", "--port", "8000"]
