"""
Testes unitários para SharePointToGCSOperator.
Cobre: execute, sanitização de paths, helpers de caminho, MIME type e envio de e-mail.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from plugins.operators.sharepoint_to_gcs_operator import SharePointToGCSOperator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FILE_META = {
    "id": "file-1",
    "name": "relatorio.xlsx",
    "size": 10240,
    "lastModifiedDateTime": "2024-02-01T10:00:00Z",
    "parentPath": "/drives/xxx/root:/Shared Documents/2024",
}


def _make_operator(**kwargs) -> SharePointToGCSOperator:
    defaults = dict(
        task_id="test_operator",
        sharepoint_conn_id="sharepoint_default",
        gcs_conn_id="google_cloud_default",
        site_url="https://company.sharepoint.com/sites/data",
        folder_path="/Shared Documents",
        gcs_bucket="my-bucket",
        gcs_prefix="raw/sharepoint",
        send_alert=False,
    )
    defaults.update(kwargs)
    return SharePointToGCSOperator(**defaults)


def _make_context(new_files=None, run_date: str = "2024/02/01") -> dict:
    if new_files is None:
        new_files = [_FILE_META]

    ti = MagicMock()
    ti.xcom_pull.return_value = new_files

    logical_date = MagicMock()
    logical_date.strftime.return_value = run_date

    dag = MagicMock()
    dag.dag_id = "sharepoint_to_gcs"

    return {
        "task_instance": ti,
        "dag": dag,
        "logical_date": logical_date,
        "run_id": "manual__2024-02-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

class TestExecute:
    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_returns_list_of_uploaded_gcs_paths(self, mock_gcs_cls, mock_sp_cls):
        mock_sp = MagicMock()
        mock_sp.download_file.return_value = b"file-data"
        mock_sp_cls.return_value = mock_sp

        mock_gcs_cls.return_value = MagicMock()

        result = _make_operator().execute(_make_context())

        assert len(result) == 1
        assert result[0].startswith("raw/sharepoint/")
        assert result[0].endswith("relatorio.xlsx")

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_calls_download_with_correct_args(self, mock_gcs_cls, mock_sp_cls):
        mock_sp = MagicMock()
        mock_sp.download_file.return_value = b"data"
        mock_sp_cls.return_value = mock_sp
        mock_gcs_cls.return_value = MagicMock()

        _make_operator().execute(_make_context())

        mock_sp.download_file.assert_called_once_with(
            site_url="https://company.sharepoint.com/sites/data",
            file_id="file-1",
        )

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_calls_gcs_upload_with_correct_bucket(self, mock_gcs_cls, mock_sp_cls):
        mock_sp = MagicMock()
        mock_sp.download_file.return_value = b"data"
        mock_sp_cls.return_value = mock_sp

        mock_gcs = MagicMock()
        mock_gcs_cls.return_value = mock_gcs

        _make_operator().execute(_make_context())

        mock_gcs.upload.assert_called_once()
        call_kwargs = mock_gcs.upload.call_args.kwargs
        assert call_kwargs["bucket_name"] == "my-bucket"

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_returns_empty_list_when_no_new_files(self, mock_gcs_cls, mock_sp_cls):
        context = _make_context(new_files=None)
        context["task_instance"].xcom_pull.return_value = None

        result = _make_operator().execute(context)

        assert result == []
        mock_sp_cls.assert_not_called()
        mock_gcs_cls.assert_not_called()

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_returns_empty_list_when_xcom_is_empty_list(self, mock_gcs_cls, mock_sp_cls):
        context = _make_context(new_files=[])

        result = _make_operator().execute(context)

        assert result == []

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_raises_runtime_error_when_all_files_fail(self, mock_gcs_cls, mock_sp_cls):
        mock_sp = MagicMock()
        mock_sp.download_file.side_effect = ConnectionError("Network error")
        mock_sp_cls.return_value = mock_sp
        mock_gcs_cls.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="Falha no upload"):
            _make_operator().execute(_make_context())

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_continues_processing_after_partial_failure(self, mock_gcs_cls, mock_sp_cls):
        """Deve processar todos os arquivos mesmo que algum falhe."""
        two_files = [
            {**_FILE_META, "id": "f1", "name": "ok.xlsx"},
            {**_FILE_META, "id": "f2", "name": "fail.xlsx"},
        ]

        mock_sp = MagicMock()
        mock_sp.download_file.side_effect = [b"data", RuntimeError("Download failed")]
        mock_sp_cls.return_value = mock_sp

        mock_gcs = MagicMock()
        mock_gcs_cls.return_value = mock_gcs

        with pytest.raises(RuntimeError, match="Falha no upload de 1"):
            _make_operator().execute(_make_context(new_files=two_files))

        # Deve ter feito upload apenas do arquivo que teve sucesso
        mock_gcs.upload.assert_called_once()

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_error_message_lists_failed_file_names(self, mock_gcs_cls, mock_sp_cls):
        mock_sp = MagicMock()
        mock_sp.download_file.side_effect = IOError("disk full")
        mock_sp_cls.return_value = mock_sp
        mock_gcs_cls.return_value = MagicMock()

        with pytest.raises(RuntimeError) as exc_info:
            _make_operator().execute(_make_context())

        assert "relatorio.xlsx" in str(exc_info.value)

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.Variable.get", return_value="smtp.gmail.com")
    def test_send_alert_called_when_flag_is_true(self, _mock_var, mock_gcs_cls, mock_sp_cls):
        mock_sp = MagicMock()
        mock_sp.download_file.return_value = b"data"
        mock_sp_cls.return_value = mock_sp
        mock_gcs_cls.return_value = MagicMock()

        operator = _make_operator(send_alert=True, alert_email="team@example.com")

        with patch.object(operator, "_send_alert_email") as mock_alert:
            operator.execute(_make_context())
            mock_alert.assert_called_once()


# ---------------------------------------------------------------------------
# _sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_valid_filename_passes_through(self):
        assert SharePointToGCSOperator._sanitize_filename("relatorio.xlsx") == "relatorio.xlsx"

    def test_filename_with_spaces_is_allowed(self):
        result = SharePointToGCSOperator._sanitize_filename("Relatório Mensal.xlsx")
        assert result == "Relatório Mensal.xlsx"

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match="vazio"):
            SharePointToGCSOperator._sanitize_filename("")

    def test_raises_on_whitespace_only(self):
        with pytest.raises(ValueError, match="vazio"):
            SharePointToGCSOperator._sanitize_filename("   ")

    def test_raises_on_null_byte(self):
        with pytest.raises(ValueError, match="byte nulo"):
            SharePointToGCSOperator._sanitize_filename("file\x00name.xlsx")

    def test_raises_on_forward_slash(self):
        with pytest.raises(ValueError, match="separador de diretório"):
            SharePointToGCSOperator._sanitize_filename("../../../etc/passwd")

    def test_raises_on_backslash(self):
        with pytest.raises(ValueError, match="separador de diretório"):
            SharePointToGCSOperator._sanitize_filename("folder\\file.xlsx")

    def test_raises_on_dot_dot(self):
        with pytest.raises(ValueError, match="inválido"):
            SharePointToGCSOperator._sanitize_filename("..")

    def test_raises_on_single_dot(self):
        with pytest.raises(ValueError, match="inválido"):
            SharePointToGCSOperator._sanitize_filename(".")

    def test_raises_on_path_traversal_attempt(self):
        with pytest.raises(ValueError, match="separador de diretório"):
            SharePointToGCSOperator._sanitize_filename("../../.env")

    def test_raises_on_absolute_path(self):
        with pytest.raises(ValueError, match="separador de diretório"):
            SharePointToGCSOperator._sanitize_filename("/etc/passwd")


# ---------------------------------------------------------------------------
# _sanitize_relative_path
# ---------------------------------------------------------------------------

class TestSanitizeRelativePath:
    def test_empty_path_returns_empty_string(self):
        assert SharePointToGCSOperator._sanitize_relative_path("") == ""

    def test_valid_path_passes_through(self):
        assert SharePointToGCSOperator._sanitize_relative_path("2024/Janeiro") == "2024/Janeiro"

    def test_normalizes_backslashes_to_forward_slashes(self):
        result = SharePointToGCSOperator._sanitize_relative_path("2024\\Janeiro")
        assert result == "2024/Janeiro"

    def test_strips_leading_and_trailing_slashes(self):
        result = SharePointToGCSOperator._sanitize_relative_path("/2024/Janeiro/")
        assert result == "2024/Janeiro"

    def test_raises_on_double_dot_component(self):
        with pytest.raises(ValueError, match="Path traversal"):
            SharePointToGCSOperator._sanitize_relative_path("2024/../secret")

    def test_raises_on_traversal_at_start(self):
        with pytest.raises(ValueError, match="Path traversal"):
            SharePointToGCSOperator._sanitize_relative_path("../../etc")

    def test_raises_on_null_byte_in_component(self):
        with pytest.raises(ValueError, match="byte nulo"):
            SharePointToGCSOperator._sanitize_relative_path("2024/Jan\x00eiro")

    def test_deeply_nested_valid_path(self):
        result = SharePointToGCSOperator._sanitize_relative_path("2024/Q1/Janeiro/Semana1")
        assert result == "2024/Q1/Janeiro/Semana1"


# ---------------------------------------------------------------------------
# execute — validação de path integrada
# ---------------------------------------------------------------------------

class TestExecuteWithInvalidPaths:
    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_file_with_path_traversal_name_is_rejected(self, mock_gcs_cls, mock_sp_cls):
        """Arquivo com nome malicioso não deve ser baixado nem enviado ao GCS."""
        malicious_file = {**_FILE_META, "name": "../../.env", "id": "evil-1"}
        context = _make_context(new_files=[malicious_file])

        with pytest.raises(RuntimeError, match="Falha no upload"):
            _make_operator().execute(context)

        mock_sp_cls.return_value.download_file.assert_not_called()
        mock_gcs_cls.return_value.upload.assert_not_called()

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_file_with_null_byte_in_name_is_rejected(self, mock_gcs_cls, mock_sp_cls):
        malicious_file = {**_FILE_META, "name": "file\x00.xlsx", "id": "evil-2"}
        context = _make_context(new_files=[malicious_file])

        with pytest.raises(RuntimeError, match="Falha no upload"):
            _make_operator().execute(context)

        mock_sp_cls.return_value.download_file.assert_not_called()

    @patch("plugins.operators.sharepoint_to_gcs_operator.SharePointHook")
    @patch("plugins.operators.sharepoint_to_gcs_operator.GCSHook")
    def test_invalid_file_rejected_but_valid_files_still_processed(
        self, mock_gcs_cls, mock_sp_cls
    ):
        """Arquivo inválido deve ser rejeitado sem bloquear os demais."""
        files = [
            {**_FILE_META, "id": "f-ok", "name": "valido.xlsx", "parentPath": "/drives/xxx/root:/Shared Documents"},
            {**_FILE_META, "id": "f-evil", "name": "../../.env", "parentPath": ""},
        ]
        mock_sp = MagicMock()
        mock_sp.download_file.return_value = b"data"
        mock_sp_cls.return_value = mock_sp
        mock_gcs_cls.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="Falha no upload de 1"):
            _make_operator().execute(_make_context(new_files=files))

        # Só o arquivo válido deve ter sido processado
        mock_sp.download_file.assert_called_once_with(
            site_url="https://company.sharepoint.com/sites/data",
            file_id="f-ok",
        )


# ---------------------------------------------------------------------------
# _build_gcs_object_path
# ---------------------------------------------------------------------------

class TestBuildGcsObjectPath:
    def test_preserves_folder_structure(self):
        operator = _make_operator(preserve_folder_structure=True)
        path = operator._build_gcs_object_path(
            run_date="2024/02/01",
            parent_path="2024/Janeiro",
            file_name="doc.xlsx",
        )
        assert path == "raw/sharepoint/2024/Janeiro/doc.xlsx"

    def test_uses_run_date_when_structure_disabled(self):
        operator = _make_operator(preserve_folder_structure=False)
        path = operator._build_gcs_object_path(
            run_date="2024/02/01",
            parent_path="2024/Janeiro",
            file_name="doc.xlsx",
        )
        assert path == "raw/sharepoint/2024/02/01/doc.xlsx"

    def test_uses_run_date_when_parent_path_empty(self):
        operator = _make_operator(preserve_folder_structure=True)
        path = operator._build_gcs_object_path(
            run_date="2024/02/01",
            parent_path="",
            file_name="doc.xlsx",
        )
        assert path == "raw/sharepoint/2024/02/01/doc.xlsx"

    def test_strips_slashes_from_prefix(self):
        operator = _make_operator(gcs_prefix="/raw/sharepoint/", preserve_folder_structure=False)
        path = operator._build_gcs_object_path(
            run_date="2024/02/01",
            parent_path="",
            file_name="doc.xlsx",
        )
        assert path == "raw/sharepoint/2024/02/01/doc.xlsx"

    def test_no_double_slashes_in_path(self):
        operator = _make_operator(preserve_folder_structure=False)
        path = operator._build_gcs_object_path(
            run_date="2024/02/01",
            parent_path="",
            file_name="doc.xlsx",
        )
        assert "//" not in path


# ---------------------------------------------------------------------------
# _extract_relative_path
# ---------------------------------------------------------------------------

class TestExtractRelativePath:
    def test_extracts_subfolder_from_graph_path(self):
        operator = _make_operator(folder_path="/Shared Documents")
        result = operator._extract_relative_path(
            "/drives/xxx/root:/Shared Documents/2024/Janeiro"
        )
        assert result == "2024/Janeiro"

    def test_root_folder_returns_empty_string(self):
        operator = _make_operator(folder_path="/Shared Documents")
        result = operator._extract_relative_path(
            "/drives/xxx/root:/Shared Documents"
        )
        assert result == ""

    def test_empty_input_returns_empty_string(self):
        assert _make_operator()._extract_relative_path("") == ""

    def test_path_without_root_marker_returns_empty(self):
        result = _make_operator()._extract_relative_path("/some/unrelated/path")
        assert result == ""

    def test_deeply_nested_subfolder(self):
        operator = _make_operator(folder_path="/Shared Documents")
        result = operator._extract_relative_path(
            "/drives/xxx/root:/Shared Documents/2024/Janeiro/Semana1"
        )
        assert result == "2024/Janeiro/Semana1"


# ---------------------------------------------------------------------------
# _guess_mime_type
# ---------------------------------------------------------------------------

class TestGuessMimeType:
    def test_pdf_returns_application_pdf(self):
        assert SharePointToGCSOperator._guess_mime_type("document.pdf") == "application/pdf"

    def test_xlsx_returns_spreadsheet_mime(self):
        mime = SharePointToGCSOperator._guess_mime_type("report.xlsx")
        assert mime is not None
        assert mime != "application/octet-stream"

    def test_unknown_extension_returns_octet_stream(self):
        assert SharePointToGCSOperator._guess_mime_type("file.xyz9999") == "application/octet-stream"

    def test_no_extension_returns_octet_stream(self):
        assert SharePointToGCSOperator._guess_mime_type("filenoextension") == "application/octet-stream"

    def test_csv_returns_text_mime(self):
        mime = SharePointToGCSOperator._guess_mime_type("data.csv")
        assert "csv" in mime or "text" in mime

    def test_jpg_returns_image_mime(self):
        mime = SharePointToGCSOperator._guess_mime_type("photo.jpg")
        assert "image" in mime


# ---------------------------------------------------------------------------
# _send_alert_email
# ---------------------------------------------------------------------------

class TestSendAlertEmail:
    def _make_context_for_email(self) -> dict:
        dag = MagicMock()
        dag.dag_id = "sharepoint_to_gcs"
        return {"dag": dag, "run_id": "manual__2024-02-01"}

    @patch("plugins.operators.sharepoint_to_gcs_operator.smtplib.SMTP")
    @patch("plugins.operators.sharepoint_to_gcs_operator.Variable.get")
    def test_sends_email_with_correct_smtp_host_and_port(self, mock_var_get, mock_smtp_cls):
        mock_var_get.side_effect = lambda key, default_var="": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "smtp_user": "sender@example.com",
            "smtp_password": "secret",
        }.get(key, default_var)

        operator = _make_operator(alert_email="team@example.com")
        operator._send_alert_email(
            uploaded=["raw/sharepoint/2024/02/01/doc.xlsx"],
            failed=[],
            run_date="2024/02/01",
            context=self._make_context_for_email(),
        )

        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587)

    @patch("plugins.operators.sharepoint_to_gcs_operator.smtplib.SMTP")
    @patch("plugins.operators.sharepoint_to_gcs_operator.Variable.get")
    def test_authenticates_and_sends_message(self, mock_var_get, mock_smtp_cls):
        mock_var_get.side_effect = lambda key, default_var="": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "smtp_user": "sender@example.com",
            "smtp_password": "secret",
        }.get(key, default_var)

        operator = _make_operator(alert_email="team@example.com")
        operator._send_alert_email(
            uploaded=["raw/sharepoint/2024/02/01/doc.xlsx"],
            failed=[],
            run_date="2024/02/01",
            context=self._make_context_for_email(),
        )

        server = mock_smtp_cls.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("sender@example.com", "secret")
        server.sendmail.assert_called_once()

    @patch("plugins.operators.sharepoint_to_gcs_operator.smtplib.SMTP")
    @patch("plugins.operators.sharepoint_to_gcs_operator.Variable.get")
    def test_smtp_failure_does_not_raise_exception(self, mock_var_get, mock_smtp_cls):
        """Falha no envio de e-mail deve apenas logar warning, não propagar."""
        mock_var_get.side_effect = lambda key, default_var="": default_var
        mock_smtp_cls.side_effect = smtplib.SMTPException("Connection refused")

        operator = _make_operator(alert_email="team@example.com")

        # Não deve levantar exceção
        operator._send_alert_email(
            uploaded=["raw/sharepoint/2024/02/01/doc.xlsx"],
            failed=[],
            run_date="2024/02/01",
            context=self._make_context_for_email(),
        )

    @patch("plugins.operators.sharepoint_to_gcs_operator.smtplib.SMTP")
    @patch("plugins.operators.sharepoint_to_gcs_operator.Variable.get")
    def test_subject_contains_warning_on_partial_failure(self, mock_var_get, mock_smtp_cls):
        mock_var_get.side_effect = lambda key, default_var="": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": "587",
            "smtp_user": "sender@example.com",
            "smtp_password": "secret",
        }.get(key, default_var)

        captured_messages = []

        def capture_sendmail(from_addr, to_addrs, msg_str):
            captured_messages.append(msg_str)

        server = mock_smtp_cls.return_value.__enter__.return_value
        server.sendmail.side_effect = capture_sendmail

        operator = _make_operator(alert_email="team@example.com")
        operator._send_alert_email(
            uploaded=["raw/sharepoint/ok.xlsx"],
            failed=["raw/sharepoint/fail.xlsx"],
            run_date="2024/02/01",
            context=self._make_context_for_email(),
        )

        assert len(captured_messages) == 1
        assert "Falha" in captured_messages[0] or "falha" in captured_messages[0].lower()
