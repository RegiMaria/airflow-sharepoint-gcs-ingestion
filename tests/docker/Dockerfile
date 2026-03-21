# docker/Dockerfile
# Imagem customizada do Airflow com dependências do projeto
# Multi-stage build para imagem final enxuta

ARG AIRFLOW_VERSION=2.9.3
ARG PYTHON_VERSION=3.11

# ---------------------------------------------------------------------------
# Stage 1: Builder — instala dependências Python
# ---------------------------------------------------------------------------
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION} AS builder

USER root

# Instala dependências do sistema necessárias para compilação
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /tmp/requirements.txt

# Instala dependências Python no diretório do usuário
RUN pip install --no-cache-dir --user -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Final — imagem de produção
# ---------------------------------------------------------------------------
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

LABEL maintainer="data-engineering@company.com"
LABEL version="1.0"
LABEL description="Airflow customizado para ingestão SharePoint → GCS"

USER root

# Instala apenas utilitários de runtime (sem dev tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Copia packages instalados do builder
COPY --from=builder /home/airflow/.local /home/airflow/.local

# Copia configuração do Airflow
COPY --chown=airflow:root config/airflow.cfg /opt/airflow/airflow.cfg

# Garante que binários do .local/bin estejam no PATH
ENV PATH="/home/airflow/.local/bin:${PATH}"

# Diretórios de trabalho
WORKDIR /opt/airflow
