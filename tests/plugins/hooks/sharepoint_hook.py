"""
Hook para integração com Microsoft SharePoint via Microsoft Graph API.
Gerencia autenticação OAuth2 e operações de listagem/download de arquivos.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Generator

import requests
from airflow.hooks.base import BaseHook
from msal import ConfidentialClientApplication

logger = logging.getLogger(__name__)


class SharePointHook(BaseHook):
    """
    Hook para Microsoft SharePoint (via Microsoft Graph API).

    Configuração da Connection no Airflow:
        - conn_type : HTTP
        - host      : https://graph.microsoft.com
        - login     : client_id (App Registration do Azure AD)
        - password  : client_secret
        - extra     : {"tenant_id": "<tenant-id>", "site_url": "<sharepoint-site-url>"}
    """

    conn_name_attr = "sharepoint_conn_id"
    default_conn_name = "sharepoint_default"
    conn_type = "http"
    hook_name = "SharePoint (Graph API)"

    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    SCOPE = ["https://graph.microsoft.com/.default"]

    def __init__(self, sharepoint_conn_id: str = default_conn_name) -> None:
        super().__init__()
        self.sharepoint_conn_id = sharepoint_conn_id
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------

    def _get_connection_config(self) -> dict[str, Any]:
        conn = self.get_connection(self.sharepoint_conn_id)
        extra = conn.extra_dejson
        return {
            "client_id": conn.login,
            "client_secret": conn.password,
            "tenant_id": extra.get("tenant_id", ""),
        }

    def get_token(self) -> str:
        """Obtém (ou renova) o token OAuth2 via MSAL."""
        now = datetime.now(tz=timezone.utc)

        if self._token and self._token_expiry and now < self._token_expiry:
            return self._token

        cfg = self._get_connection_config()
        authority = f"https://login.microsoftonline.com/{cfg['tenant_id']}"

        app = ConfidentialClientApplication(
            client_id=cfg["client_id"],
            client_credential=cfg["client_secret"],
            authority=authority,
        )

        result = app.acquire_token_for_client(scopes=self.SCOPE)

        if "access_token" not in result:
            raise RuntimeError(
                f"Falha ao obter token do Azure AD: {result.get('error_description')}"
            )

        self._token = result["access_token"]
        expires_in = result.get("expires_in", 3600)
        from datetime import timedelta
        self._token_expiry = now + timedelta(seconds=expires_in - 60)

        logger.info("Token OAuth2 obtido com sucesso.")
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}

    # ------------------------------------------------------------------
    # Operações Graph API
    # ------------------------------------------------------------------

    def _get_site_id(self, site_url: str) -> str:
        """Resolve o site_id a partir da URL do SharePoint."""
        from urllib.parse import urlparse
        parsed = urlparse(site_url)
        hostname = parsed.netloc
        site_path = parsed.path.rstrip("/")

        url = f"{self.GRAPH_API_BASE}/sites/{hostname}:{site_path}"
        response = requests.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()["id"]

    def _get_drive_id(self, site_id: str) -> str:
        """Obtém o drive padrão do site."""
        url = f"{self.GRAPH_API_BASE}/sites/{site_id}/drive"
        response = requests.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()["id"]

    def list_files(
        self,
        site_url: str,
        folder_path: str,
        modified_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista arquivos em uma pasta do SharePoint.

        Args:
            site_url: URL do site SharePoint.
            folder_path: Caminho relativo da pasta.
            modified_since: Filtra arquivos modificados após esta data.

        Returns:
            Lista de metadados de arquivos.
        """
        site_id = self._get_site_id(site_url)
        drive_id = self._get_drive_id(site_id)

        folder = folder_path.strip("/")
        url = (
            f"{self.GRAPH_API_BASE}/drives/{drive_id}"
            f"/root:/{folder}:/children"
            "?$select=id,name,size,lastModifiedDateTime,file,parentReference"
            "&$top=999"
        )

        all_files: list[dict[str, Any]] = []

        while url:
            response = requests.get(url, headers=self._headers(), timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get("value", []):
                # Ignora pastas (sem a propriedade "file")
                if "file" not in item:
                    continue

                if modified_since:
                    item_modified = datetime.fromisoformat(
                        item["lastModifiedDateTime"].replace("Z", "+00:00")
                    )
                    if item_modified <= modified_since:
                        continue

                all_files.append(item)

            url = data.get("@odata.nextLink")

        logger.info("Encontrados %d arquivo(s) em '%s'.", len(all_files), folder_path)
        return all_files

    def download_file(self, site_url: str, file_id: str) -> bytes:
        """Faz download do conteúdo de um arquivo pelo seu ID."""
        site_id = self._get_site_id(site_url)
        drive_id = self._get_drive_id(site_id)

        url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/items/{file_id}/content"
        response = requests.get(url, headers=self._headers(), timeout=120, stream=True)
        response.raise_for_status()

        return response.content

    def iter_file_chunks(
        self, site_url: str, file_id: str, chunk_size: int = 8 * 1024 * 1024
    ) -> Generator[bytes, None, None]:
        """Itera sobre chunks de um arquivo (útil para arquivos grandes)."""
        site_id = self._get_site_id(site_url)
        drive_id = self._get_drive_id(site_id)

        url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/items/{file_id}/content"
        with requests.get(url, headers=self._headers(), timeout=120, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=chunk_size):
                yield chunk
