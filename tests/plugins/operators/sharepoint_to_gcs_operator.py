"""
Operator que transfere arquivos do SharePoint para o GCS.
Lê a lista de arquivos do XCom do sensor upstream e faz o upload.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import PurePosixPath
from typing import Any

import requests.exceptions
from google.api_core import exceptions as google_exceptions

from airflow.models import Variable
from airflow.models.baseoperator import BaseOperator
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.utils.context import Context

from plugins.hooks.sharepoint_hook import SharePointHook
from plugins.sensors.sharepoint_new_files_sensor import XCOM_NEW_FILES_KEY

logger = logging.getLogger(__name__)


class SharePointToGCSOperator(BaseOperator):
    """
    Transfere arquivos do SharePoint para o Google Cloud Storage.

    - Lê lista de novos arquivos via XCom do sensor upstream.
    - Faz upload respeitando (ou não) a estrutura de pastas original.
    - Envia e-mail de alerta com o resumo dos arquivos ingeridos.
    - Idempotente: registra arquivos já processados via Airflow Variable.

    Args:
        sharepoint_conn_id: Connection Airflow para o SharePoint.
        gcs_conn_id: Connection Airflow para o GCS.
        site_url: URL do site SharePoint.
        folder_path: Pasta raiz monitorada no SharePoint.
        gcs_bucket: Nome do bucket GCS de destino.
        gcs_prefix: Prefixo (pasta) dentro do bucket.
        preserve_folder_structure: Mantém estrutura de pastas do SharePoint no GCS.
        send_alert: Envia e-mail de notificação após a ingestão.
        alert_email: Destinatário(s) do alerta (separados por vírgula).
    """

    template_fields = ("site_url", "folder_path", "gcs_bucket", "gcs_prefix")

    def __init__(
        self,
        sharepoint_conn_id: str,
        gcs_conn_id: str,
        site_url: str,
        folder_path: str,
        gcs_bucket: str,
        gcs_prefix: str = "raw/sharepoint",
        preserve_folder_structure: bool = True,
        send_alert: bool = True,
        alert_email: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.sharepoint_conn_id = sharepoint_conn_id
        self.gcs_conn_id = gcs_conn_id
        self.site_url = site_url
        self.folder_path = folder_path
        self.gcs_bucket = gcs_bucket
        self.gcs_prefix = gcs_prefix
        self.preserve_folder_structure = preserve_folder_structure
        self.send_alert = send_alert
        self.alert_email = alert_email

    def execute(self, context: Context) -> list[str]:
        """Executa a transferência. Retorna lista de GCS objects criados."""

        # Obtém lista de arquivos do sensor via XCom
        new_files: list[dict[str, Any]] = context["task_instance"].xcom_pull(
            task_ids="check_new_files_sharepoint",
            key=XCOM_NEW_FILES_KEY,
        )

        if not new_files:
            logger.info("Nenhum arquivo novo para processar.")
            return []

        sp_hook = SharePointHook(sharepoint_conn_id=self.sharepoint_conn_id)
        gcs_hook = GCSHook(gcp_conn_id=self.gcs_conn_id)

        uploaded: list[str] = []
        failed: list[str] = []

        run_date = context["logical_date"].strftime("%Y/%m/%d")

        for file_meta in new_files:
            raw_name = file_meta["name"]
            file_id = file_meta["id"]
            raw_parent = self._extract_relative_path(file_meta.get("parentPath", ""))

            try:
                file_name = self._sanitize_filename(raw_name)
                parent_path = self._sanitize_relative_path(raw_parent)
            except ValueError as exc:
                logger.warning(
                    "Arquivo '%s' ignorado: nome ou caminho inválido. Detalhes: %s",
                    raw_name,
                    exc,
                )
                failed.append(raw_name)
                continue

            gcs_object = self._build_gcs_object_path(
                run_date=run_date,
                parent_path=parent_path,
                file_name=file_name,
            )

            try:
                logger.info("Fazendo download: %s", file_name)
                content: bytes = sp_hook.download_file(
                    site_url=self.site_url,
                    file_id=file_id,
                )

                logger.info("Fazendo upload para gs://%s/%s", self.gcs_bucket, gcs_object)
                gcs_hook.upload(
                    bucket_name=self.gcs_bucket,
                    object_name=gcs_object,
                    data=content,
                    mime_type=self._guess_mime_type(file_name),
                )

                uploaded.append(gcs_object)
                logger.info("Upload concluído: %s", gcs_object)

            except (
                requests.exceptions.RequestException,
                google_exceptions.GoogleAPICallError,
                OSError,
            ) as exc:
                logger.exception("Falha ao processar '%s': %s", file_name, exc)
                failed.append(file_name)

        # Alerta de notificação
        if self.send_alert and (uploaded or failed):
            self._send_alert_email(
                uploaded=uploaded,
                failed=failed,
                run_date=run_date,
                context=context,
            )

        if failed:
            raise RuntimeError(
                f"Falha no upload de {len(failed)} arquivo(s): {failed}"
            )

        logger.info(
            "Ingestão concluída. %d arquivo(s) enviados ao GCS.", len(uploaded)
        )
        return uploaded

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_relative_path(self, graph_path: str) -> str:
        """
        Extrai caminho relativo a partir do parentReference.path do Graph API.
        Exemplo: '/drives/xxx/root:/Shared Documents/2024/Janeiro'
                  → '2024/Janeiro'
        """
        if not graph_path:
            return ""
        # O caminho vem como /drives/<id>/root:/<folder>
        root_marker = "root:/"
        if root_marker in graph_path:
            after_root = graph_path.split(root_marker, 1)[1]
            base_folder = self.folder_path.strip("/")
            relative = after_root.replace(base_folder, "", 1).strip("/")
            return relative
        return ""

    def _build_gcs_object_path(
        self, run_date: str, parent_path: str, file_name: str
    ) -> str:
        """Monta o caminho completo do objeto no GCS."""
        parts = [self.gcs_prefix.strip("/")]

        if self.preserve_folder_structure and parent_path:
            parts.append(parent_path.strip("/"))
        else:
            parts.append(run_date)

        parts.append(file_name)
        return "/".join(p for p in parts if p)

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        Valida e sanitiza o nome de arquivo vindo do SharePoint antes de usá-lo
        como componente de path no GCS.

        Rejeita (lança ValueError) nomes que contenham:
        - Bytes nulos
        - Separadores de diretório embutidos (/ ou \\)
        - Sequências de path traversal (..)

        Args:
            name: Nome de arquivo bruto do SharePoint.

        Returns:
            Nome sanitizado, pronto para uso como componente de path.

        Raises:
            ValueError: Se o nome for inválido ou potencialmente malicioso.
        """
        if not name or not name.strip():
            raise ValueError("Nome de arquivo vazio ou só com espaços.")

        if "\x00" in name:
            raise ValueError(f"Nome contém byte nulo: {name!r}")

        # Barras invertidas são separadores de diretório no Windows
        if "\\" in name or "/" in name:
            raise ValueError(
                f"Nome de arquivo contém separador de diretório: {name!r}. "
                "Apenas o nome do arquivo (sem caminho) é permitido."
            )

        if name.strip() in (".", ".."):
            raise ValueError(f"Nome de arquivo inválido: {name!r}")

        return name

    @staticmethod
    def _sanitize_relative_path(path: str) -> str:
        """
        Valida e sanitiza o caminho relativo de pasta extraído do SharePoint.

        Rejeita (lança ValueError) caminhos que contenham:
        - Componentes '..' (path traversal)
        - Bytes nulos

        Args:
            path: Caminho relativo já extraído (ex: '2024/Janeiro').

        Returns:
            Caminho sanitizado, ou string vazia para a raiz.

        Raises:
            ValueError: Se o caminho contiver tentativa de path traversal.
        """
        if not path:
            return ""

        # Normaliza separadores (defensivo contra valores vindos via XCom)
        path = path.replace("\\", "/")

        components = [p for p in path.split("/") if p]

        for part in components:
            if "\x00" in part:
                raise ValueError(f"Componente de caminho contém byte nulo: {part!r}")
            if part == "..":
                raise ValueError(
                    f"Path traversal detectado no caminho de pasta: {path!r}"
                )

        return "/".join(components)

    @staticmethod
    def _guess_mime_type(file_name: str) -> str:
        import mimetypes
        mime, _ = mimetypes.guess_type(file_name)
        return mime or "application/octet-stream"

    def _send_alert_email(
        self,
        uploaded: list[str],
        failed: list[str],
        run_date: str,
        context: Context,
    ) -> None:
        """Envia e-mail de alerta com o resumo da ingestão."""
        dag_id = context["dag"].dag_id
        run_id = context["run_id"]

        subject = (
            f"[Airflow] Novos documentos ingeridos do SharePoint - {run_date}"
            if not failed
            else f"[Airflow] ⚠️ Falha parcial na ingestão SharePoint → GCS - {run_date}"
        )

        body_lines = [
            f"<h3>Ingestão SharePoint → GCS</h3>",
            f"<b>DAG:</b> {dag_id}<br>",
            f"<b>Run ID:</b> {run_id}<br>",
            f"<b>Data:</b> {run_date}<br>",
            f"<b>Bucket destino:</b> gs://{self.gcs_bucket}/{self.gcs_prefix}<br><br>",
        ]

        if uploaded:
            body_lines.append(f"<b>✅ {len(uploaded)} arquivo(s) ingerido(s) com sucesso:</b><ul>")
            for obj in uploaded:
                body_lines.append(f"<li><code>{obj}</code></li>")
            body_lines.append("</ul>")

        if failed:
            body_lines.append(f"<b>❌ {len(failed)} arquivo(s) com falha:</b><ul>")
            for name in failed:
                body_lines.append(f"<li><code>{name}</code></li>")
            body_lines.append("</ul>")

        try:
            smtp_host = Variable.get("smtp_host", default_var="smtp.gmail.com")
            smtp_port = int(Variable.get("smtp_port", default_var="587"))
            smtp_user = Variable.get("smtp_user", default_var="")
            smtp_password = Variable.get("smtp_password", default_var="")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = self.alert_email
            msg.attach(MIMEText("".join(body_lines), "html"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(smtp_user, self.alert_email.split(","), msg.as_string())

            logger.info("E-mail de alerta enviado para %s.", self.alert_email)

        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("Não foi possível enviar o e-mail de alerta: %s", exc)
