# docker/Dockerfile
ARG AIRFLOW_VERSION=2.9.3
ARG PYTHON_VERSION=3.11

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

LABEL maintainer="data-engineering@company.com"
LABEL version="1.0"
LABEL description="Airflow customizado para ingestão SharePoint → GCS"

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PATH="/home/airflow/.local/bin:${PATH}"
WORKDIR /opt/airflow
