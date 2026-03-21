"""
Testes unitários para SharePointNewFilesSensor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from plugins.sensors.sharepoint_new_files_sensor import (
    XCOM_NEW_FILES_KEY,
    SharePointNewFilesSensor,
)


MOCK_FILES = [
    {
        "id": "abc123",
        "name": "relatorio_janeiro.xlsx",
        "size": 102400,
        "lastModifiedDateTime": "2024-02-01T10:00:00Z",
        "parentReference": {"path": "/drives/xxx/root:/Shared Documents"},
        "file": {},
    }
]


def _make_sensor(**kwargs) -> SharePointNewFilesSensor:
    defaults = dict(
        task_id="test_sensor",
        sharepoint_conn_id="sharepoint_default",
        site_url="https://company.sharepoint.com/sites/data",
        folder_path="/Shared Documents",
        poke_interval=60,
        timeout=300,
    )
    defaults.update(kwargs)
    return SharePointNewFilesSensor(**defaults)


class TestSharePointNewFilesSensor:
    @patch("plugins.sensors.sharepoint_new_files_sensor.SharePointHook")
    def test_poke_returns_true_when_files_found(self, mock_hook_cls):
        mock_hook = MagicMock()
        mock_hook.list_files.return_value = MOCK_FILES
        mock_hook_cls.return_value = mock_hook

        sensor = _make_sensor()
        context = {
            "data_interval_start": datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc),
            "task_instance": MagicMock(),
        }

        result = sensor.poke(context)

        assert result is True
        context["task_instance"].xcom_push.assert_called_once()
        call_kwargs = context["task_instance"].xcom_push.call_args.kwargs
        assert call_kwargs["key"] == XCOM_NEW_FILES_KEY
        assert len(call_kwargs["value"]) == 1

    @patch("plugins.sensors.sharepoint_new_files_sensor.SharePointHook")
    def test_poke_returns_false_when_no_files(self, mock_hook_cls):
        mock_hook = MagicMock()
        mock_hook.list_files.return_value = []
        mock_hook_cls.return_value = mock_hook

        sensor = _make_sensor()
        context = {
            "data_interval_start": datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc),
            "task_instance": MagicMock(),
        }

        result = sensor.poke(context)

        assert result is False
        context["task_instance"].xcom_push.assert_not_called()

    @patch("plugins.sensors.sharepoint_new_files_sensor.SharePointHook")
    def test_poke_passes_modified_since_to_hook(self, mock_hook_cls):
        mock_hook = MagicMock()
        mock_hook.list_files.return_value = []
        mock_hook_cls.return_value = mock_hook

        sensor = _make_sensor()
        start = datetime(2024, 3, 15, 8, 30, tzinfo=timezone.utc)
        context = {
            "data_interval_start": start,
            "task_instance": MagicMock(),
        }

        sensor.poke(context)

        mock_hook.list_files.assert_called_once_with(
            site_url="https://company.sharepoint.com/sites/data",
            folder_path="/Shared Documents",
            modified_since=start,
        )
