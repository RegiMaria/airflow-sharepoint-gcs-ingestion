"""
DAG: sharepoint_to_gcs
Descrição: Detecta novos documentos no SharePoint e os ingere no GCS (Data Lake).
Schedule: A cada 30 minutos (configurável via variável do Airflow).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule

from operators.sharepoint_to_gcs_operator import SharePointToGCSOperator
from sensors.sharepoint_new_files_sensor import SharePointNewFilesSensor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurações padrão
# ---------------------------------------------------------------------------
DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email": Variable.get("alert_email", default_var="data-team@company.com").split(","),
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}

SHAREPOINT_CONN_ID = "sharepoint_default"
GCS_CONN_ID = "google_cloud_default"

SHAREPOINT_SITE = Variable.get("sharepoint_site_url", default_var="")
SHAREPOINT_FOLDER = Variable.get("sharepoint_folder_path", default_var="/Shared Documents")
GCS_BUCKET = Variable.get("gcs_datalake_bucket", default_var="my-datalake-bucket")
GCS_PREFIX = Variable.get("gcs_destination_prefix", default_var="raw/sharepoint")

SCHEDULE_INTERVAL = Variable.get("sharepoint_sync_schedule", default_var="*/30 * * * *")

# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------
with DAG(
    dag_id="sharepoint_to_gcs",
    default_args=DEFAULT_ARGS,
    description="Detecta e ingere novos documentos do SharePoint para o GCS",
    schedule_interval=SCHEDULE_INTERVAL,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sharepoint", "gcs", "ingestion", "datalake"],
    doc_md=__doc__,
    params={
        "sharepoint_site": SHAREPOINT_SITE,
        "sharepoint_folder": SHAREPOINT_FOLDER,
        "gcs_bucket": GCS_BUCKET,
        "gcs_prefix": GCS_PREFIX,
    },
) as dag:

    start = EmptyOperator(task_id="start")

    # Sensor: aguarda/detecta novos arquivos no SharePoint
    check_new_files = SharePointNewFilesSensor(
        task_id="check_new_files_sharepoint",
        sharepoint_conn_id=SHAREPOINT_CONN_ID,
        site_url=SHAREPOINT_SITE,
        folder_path=SHAREPOINT_FOLDER,
        poke_interval=60,          # verifica a cada 60s
        timeout=60 * 25,           # timeout antes do próximo ciclo (25 min)
        mode="reschedule",         # libera o worker enquanto aguarda
        soft_fail=True,            # não falha o DAG se não houver arquivos novos
    )

    # Operator: copia os novos arquivos para o GCS
    ingest_to_gcs = SharePointToGCSOperator(
        task_id="ingest_files_to_gcs",
        sharepoint_conn_id=SHAREPOINT_CONN_ID,
        gcs_conn_id=GCS_CONN_ID,
        site_url=SHAREPOINT_SITE,
        folder_path=SHAREPOINT_FOLDER,
        gcs_bucket=GCS_BUCKET,
        gcs_prefix=GCS_PREFIX,
        # Preserva estrutura de pastas do SharePoint no GCS
        preserve_folder_structure=True,
        # Envia notificação de alerta após ingestão bem-sucedida
        send_alert=True,
        alert_email=Variable.get("alert_email", default_var="data-team@company.com"),
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    start >> check_new_files >> ingest_to_gcs >> end
