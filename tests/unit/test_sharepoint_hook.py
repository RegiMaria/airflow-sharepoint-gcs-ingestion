"""
Testes unitários para SharePointHook.
Cobre: autenticação OAuth2, listagem de arquivos, paginação e download.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest
import requests as req

from plugins.hooks.sharepoint_hook import SharePointHook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hook(conn_id: str = "sharepoint_default") -> SharePointHook:
    return SharePointHook(sharepoint_conn_id=conn_id)


def _mock_connection(
    client_id: str = "test-client",
    client_secret: str = "test-secret",
    tenant_id: str = "test-tenant",
) -> MagicMock:
    conn = MagicMock()
    conn.login = client_id
    conn.password = client_secret
    conn.extra_dejson = {"tenant_id": tenant_id}
    return conn


def _make_response(data: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = data
    response.raise_for_status = MagicMock()
    return response


# ---------------------------------------------------------------------------
# Autenticação – get_token
# ---------------------------------------------------------------------------

class TestGetToken:
    @patch("plugins.hooks.sharepoint_hook.ConfidentialClientApplication")
    @patch.object(SharePointHook, "get_connection")
    def test_acquires_new_token(self, mock_get_conn, mock_msal_cls):
        mock_get_conn.return_value = _mock_connection()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "token-abc",
            "expires_in": 3600,
        }
        mock_msal_cls.return_value = mock_app

        hook = _make_hook()
        token = hook.get_token()

        assert token == "token-abc"
        mock_app.acquire_token_for_client.assert_called_once_with(scopes=SharePointHook.SCOPE)

    @patch("plugins.hooks.sharepoint_hook.ConfidentialClientApplication")
    @patch.object(SharePointHook, "get_connection")
    def test_returns_cached_token_when_valid(self, mock_get_conn, mock_msal_cls):
        mock_get_conn.return_value = _mock_connection()

        hook = _make_hook()
        hook._token = "cached-token"
        hook._token_expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)

        token = hook.get_token()

        assert token == "cached-token"
        mock_msal_cls.assert_not_called()

    @patch("plugins.hooks.sharepoint_hook.ConfidentialClientApplication")
    @patch.object(SharePointHook, "get_connection")
    def test_refreshes_expired_token(self, mock_get_conn, mock_msal_cls):
        mock_get_conn.return_value = _mock_connection()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }
        mock_msal_cls.return_value = mock_app

        hook = _make_hook()
        hook._token = "expired-token"
        hook._token_expiry = datetime.now(tz=timezone.utc) - timedelta(seconds=1)

        token = hook.get_token()

        assert token == "new-token"
        mock_app.acquire_token_for_client.assert_called_once()

    @patch("plugins.hooks.sharepoint_hook.ConfidentialClientApplication")
    @patch.object(SharePointHook, "get_connection")
    def test_raises_runtime_error_on_auth_failure(self, mock_get_conn, mock_msal_cls):
        mock_get_conn.return_value = _mock_connection()
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Client authentication failed.",
        }
        mock_msal_cls.return_value = mock_app

        hook = _make_hook()

        with pytest.raises(RuntimeError, match="Falha ao obter token"):
            hook.get_token()

    @patch("plugins.hooks.sharepoint_hook.ConfidentialClientApplication")
    @patch.object(SharePointHook, "get_connection")
    def test_builds_authority_url_from_tenant_id(self, mock_get_conn, mock_msal_cls):
        mock_get_conn.return_value = _mock_connection(tenant_id="my-tenant-id")
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "token",
            "expires_in": 3600,
        }
        mock_msal_cls.return_value = mock_app

        _make_hook().get_token()

        mock_msal_cls.assert_called_once()
        _, kwargs = mock_msal_cls.call_args
        assert "my-tenant-id" in kwargs.get("authority", mock_msal_cls.call_args[0][2] if len(mock_msal_cls.call_args[0]) > 2 else "")


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

class TestListFiles:
    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_returns_only_file_items(self, _mock_token, mock_get):
        """Pastas (itens sem propriedade 'file') devem ser ignoradas."""
        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            _make_response({
                "value": [
                    {"id": "f1", "name": "doc.xlsx", "size": 100,
                     "lastModifiedDateTime": "2024-02-01T10:00:00Z",
                     "file": {}, "parentReference": {}},
                    {"id": "f2", "name": "SubFolder", "size": 0,
                     "lastModifiedDateTime": "2024-02-01T10:00:00Z",
                     "parentReference": {}},  # pasta — sem "file"
                ]
            }),
        ]

        result = _make_hook().list_files(
            site_url="https://company.sharepoint.com/sites/data",
            folder_path="/Shared Documents",
        )

        assert len(result) == 1
        assert result[0]["name"] == "doc.xlsx"

    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_filters_files_by_modified_since(self, _mock_token, mock_get):
        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            _make_response({
                "value": [
                    {"id": "f1", "name": "new.xlsx", "size": 100,
                     "lastModifiedDateTime": "2024-02-02T10:00:00Z",
                     "file": {}, "parentReference": {}},
                    {"id": "f2", "name": "old.xlsx", "size": 100,
                     "lastModifiedDateTime": "2024-01-01T10:00:00Z",
                     "file": {}, "parentReference": {}},
                ]
            }),
        ]

        cutoff = datetime(2024, 2, 1, tzinfo=timezone.utc)
        result = _make_hook().list_files(
            site_url="https://company.sharepoint.com/sites/data",
            folder_path="/Shared Documents",
            modified_since=cutoff,
        )

        assert len(result) == 1
        assert result[0]["name"] == "new.xlsx"

    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_includes_file_modified_exactly_at_cutoff_boundary(self, _mock_token, mock_get):
        """Arquivo modificado exatamente no cutoff deve ser EXCLUÍDO (<=)."""
        cutoff = datetime(2024, 2, 1, 10, 0, 0, tzinfo=timezone.utc)

        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            _make_response({
                "value": [
                    {"id": "f1", "name": "boundary.xlsx", "size": 100,
                     "lastModifiedDateTime": "2024-02-01T10:00:00Z",
                     "file": {}, "parentReference": {}},
                ]
            }),
        ]

        result = _make_hook().list_files(
            site_url="https://company.sharepoint.com/sites/data",
            folder_path="/Shared Documents",
            modified_since=cutoff,
        )

        assert len(result) == 0

    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_handles_pagination_via_next_link(self, _mock_token, mock_get):
        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            _make_response({
                "value": [
                    {"id": "f1", "name": "a.xlsx", "size": 10,
                     "lastModifiedDateTime": "2024-02-01T10:00:00Z",
                     "file": {}, "parentReference": {}},
                ],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/page2",
            }),
            _make_response({
                "value": [
                    {"id": "f2", "name": "b.xlsx", "size": 10,
                     "lastModifiedDateTime": "2024-02-01T11:00:00Z",
                     "file": {}, "parentReference": {}},
                ]
            }),
        ]

        result = _make_hook().list_files(
            site_url="https://company.sharepoint.com/sites/data",
            folder_path="/Shared Documents",
        )

        assert len(result) == 2
        assert {r["name"] for r in result} == {"a.xlsx", "b.xlsx"}

    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_returns_empty_list_for_empty_folder(self, _mock_token, mock_get):
        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            _make_response({"value": []}),
        ]

        result = _make_hook().list_files(
            site_url="https://company.sharepoint.com/sites/data",
            folder_path="/Shared Documents",
        )

        assert result == []

    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_raises_http_error_on_bad_response(self, _mock_token, mock_get):
        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = req.HTTPError("403 Forbidden")

        mock_get.side_effect = [error_resp]

        with pytest.raises(req.HTTPError):
            _make_hook().list_files(
                site_url="https://company.sharepoint.com/sites/data",
                folder_path="/Shared Documents",
            )


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------

class TestDownloadFile:
    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_returns_file_bytes(self, _mock_token, mock_get):
        content_resp = MagicMock()
        content_resp.content = b"binary file content"
        content_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            content_resp,
        ]

        result = _make_hook().download_file(
            site_url="https://company.sharepoint.com/sites/data",
            file_id="file-789",
        )

        assert result == b"binary file content"

    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_raises_http_error_on_missing_file(self, _mock_token, mock_get):
        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = req.HTTPError("404 Not Found")

        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            error_resp,
        ]

        with pytest.raises(req.HTTPError):
            _make_hook().download_file(
                site_url="https://company.sharepoint.com/sites/data",
                file_id="missing-file",
            )


# ---------------------------------------------------------------------------
# iter_file_chunks
# ---------------------------------------------------------------------------

class TestIterFileChunks:
    @patch("plugins.hooks.sharepoint_hook.requests.get")
    @patch.object(SharePointHook, "get_token", return_value="fake-token")
    def test_yields_chunks(self, _mock_token, mock_get):
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        chunk_resp = MagicMock()
        chunk_resp.raise_for_status = MagicMock()
        chunk_resp.iter_content.return_value = iter(chunks)
        chunk_resp.__enter__ = MagicMock(return_value=chunk_resp)
        chunk_resp.__exit__ = MagicMock(return_value=False)

        mock_get.side_effect = [
            _make_response({"id": "site-123"}),
            _make_response({"id": "drive-456"}),
            chunk_resp,
        ]

        result = list(_make_hook().iter_file_chunks(
            site_url="https://company.sharepoint.com/sites/data",
            file_id="file-789",
        ))

        assert result == chunks
