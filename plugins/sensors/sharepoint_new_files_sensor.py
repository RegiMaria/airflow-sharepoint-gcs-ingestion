"""
Sensor que detecta novos arquivos em uma pasta do SharePoint.
Usa XCom para passar a lista de arquivos detectados para o próximo task.
"""

from __future__ import annotations

import logging
from datetime import datetime

from airflow.sensors.base import BaseSensorOperator
from airflow.utils.context import Context

from hooks.sharepoint_hook import SharePointHook

logger = logging.getLogger(__name__)

# Chave XCom para compartilhar a lista de novos arquivos
XCOM_NEW_FILES_KEY = "new_files"


class SharePointNewFilesSensor(BaseSensorOperator):
    """
    Sensor que verifica a existência de novos arquivos no SharePoint.

    Ao detectar arquivos, empurra a lista para XCom sob a chave
    ``new_files`` para ser consumida pelo SharePointToGCSOperator.

    Args:
        sharepoint_conn_id: ID da connection do Airflow para o SharePoint.
        site_url: URL do site SharePoint.
        folder_path: Caminho da pasta a monitorar.
    """

    template_fields = ("site_url", "folder_path")

    def __init__(
        self,
        sharepoint_conn_id: str,
        site_url: str,
        folder_path: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.sharepoint_conn_id = sharepoint_conn_id
        self.site_url = site_url
        self.folder_path = folder_path

    def poke(self, context: Context) -> bool:
        """
        Verifica novos arquivos. Retorna True se encontrar algum.

        - Em execuções normais (schedule), usa data_interval_start como janela.
        - Em triggers manuais com backfill_from, usa essa data para buscar
          arquivos desde uma data específica (útil para carga inicial).
        """
        hook = SharePointHook(sharepoint_conn_id=self.sharepoint_conn_id)

        # Janela normal: desde o início do intervalo atual de execução
        # modified_since: datetime = context["data_interval_start"]

        # Backfill: se informado via params, usa essa data como ponto de partida
        # Útil para trigger manual que precisa buscar arquivos desde 2025-01-01
        backfill_from = context["params"].get("backfill_from")
        if backfill_from:
            modified_since = datetime.fromisoformat(backfill_from)
        else:
            modified_since = context["data_interval_start"]

        logger.info(
            "Verificando arquivos em '%s' modificados após %s",
            self.folder_path,
            modified_since.isoformat(),
        )

        new_files = hook.list_files(
            site_url=self.site_url,
            folder_path=self.folder_path,
            modified_since=modified_since,
        )

        if not new_files:
            logger.info("Nenhum arquivo novo encontrado. Aguardando próximo ciclo.")
            return False

        logger.info("%d arquivo(s) novo(s) detectado(s).", len(new_files))

        # Empurra metadados para XCom — o operador downstream usa isso
        context["task_instance"].xcom_push(
            key=XCOM_NEW_FILES_KEY,
            value=[
                {
                    "id": f["id"],
                    "name": f["name"],
                    "size": f["size"],
                    "lastModifiedDateTime": f["lastModifiedDateTime"],
                    "parentPath": f.get("parentReference", {}).get("path", ""),
                }
                for f in new_files
            ],
        )

        return True