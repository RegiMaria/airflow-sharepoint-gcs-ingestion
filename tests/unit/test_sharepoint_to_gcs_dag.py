"""
Testes de estrutura para o DAG sharepoint_to_gcs.
Valida tasks, dependências, configurações e ausência de erros de importação.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

# Caminho absoluto para o arquivo do DAG
_DAG_FILE = Path(__file__).parents[2] / "dags" / "sharepoint_to_gcs_dag.py"
_MODULE_NAME = "sharepoint_to_gcs_dag"


def _load_dag_module():
    """
    Carrega (ou recarrega) o módulo do DAG via importlib.
    Necessário porque `dags/` não é um package Python (sem __init__.py),
    e o DAG chama Variable.get em nível de módulo ao importar.
    O mock de Variable.get deve estar ativo ANTES desta chamada.
    """
    # Remove cache para forçar re-execução do módulo com o mock ativo
    if _MODULE_NAME in sys.modules:
        del sys.modules[_MODULE_NAME]

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Testes de estrutura
# ---------------------------------------------------------------------------

class TestDagStructure:
    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_loads_without_errors(self, _mock_var):
        dag_module = _load_dag_module()
        assert dag_module.dag is not None

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_has_four_tasks(self, _mock_var):
        dag_module = _load_dag_module()
        assert len(dag_module.dag.tasks) == 4

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_task_ids_are_correct(self, _mock_var):
        dag_module = _load_dag_module()
        task_ids = {task.task_id for task in dag_module.dag.tasks}
        assert task_ids == {
            "start",
            "check_new_files_sharepoint",
            "ingest_files_to_gcs",
            "end",
        }

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_id_is_correct(self, _mock_var):
        dag_module = _load_dag_module()
        assert dag_module.dag.dag_id == "sharepoint_to_gcs"

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_catchup_is_false(self, _mock_var):
        dag_module = _load_dag_module()
        assert dag_module.dag.catchup is False

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_max_active_runs_is_one(self, _mock_var):
        dag_module = _load_dag_module()
        assert dag_module.dag.max_active_runs == 1


# ---------------------------------------------------------------------------
# Testes de dependências (task ordering)
# ---------------------------------------------------------------------------

class TestDagDependencies:
    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_start_feeds_sensor(self, _mock_var):
        dag = _load_dag_module().dag
        start = dag.get_task("start")
        downstream_ids = {t.task_id for t in start.downstream_list}
        assert "check_new_files_sharepoint" in downstream_ids

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_sensor_feeds_operator(self, _mock_var):
        dag = _load_dag_module().dag
        sensor = dag.get_task("check_new_files_sharepoint")
        downstream_ids = {t.task_id for t in sensor.downstream_list}
        assert "ingest_files_to_gcs" in downstream_ids

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_operator_feeds_end(self, _mock_var):
        dag = _load_dag_module().dag
        operator = dag.get_task("ingest_files_to_gcs")
        downstream_ids = {t.task_id for t in operator.downstream_list}
        assert "end" in downstream_ids

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_full_pipeline_order(self, _mock_var):
        """Valida a ordem completa: start → sensor → operator → end."""
        dag = _load_dag_module().dag

        def upstream_ids(task_id: str) -> set[str]:
            return {t.task_id for t in dag.get_task(task_id).upstream_list}

        assert "start" in upstream_ids("check_new_files_sharepoint")
        assert "check_new_files_sharepoint" in upstream_ids("ingest_files_to_gcs")
        assert "ingest_files_to_gcs" in upstream_ids("end")


# ---------------------------------------------------------------------------
# Testes de configuração do sensor
# ---------------------------------------------------------------------------

class TestSensorConfiguration:
    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_sensor_uses_reschedule_mode(self, _mock_var):
        dag = _load_dag_module().dag
        sensor = dag.get_task("check_new_files_sharepoint")
        assert sensor.mode == "reschedule"

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_sensor_soft_fail_is_enabled(self, _mock_var):
        dag = _load_dag_module().dag
        sensor = dag.get_task("check_new_files_sharepoint")
        assert sensor.soft_fail is True

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_sensor_poke_interval_is_60_seconds(self, _mock_var):
        dag = _load_dag_module().dag
        sensor = dag.get_task("check_new_files_sharepoint")
        assert sensor.poke_interval == 60

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_sensor_timeout_is_25_minutes(self, _mock_var):
        dag = _load_dag_module().dag
        sensor = dag.get_task("check_new_files_sharepoint")
        assert sensor.timeout == 60 * 25


# ---------------------------------------------------------------------------
# Testes de configuração do operator
# ---------------------------------------------------------------------------

class TestOperatorConfiguration:
    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_operator_preserve_folder_structure_is_true(self, _mock_var):
        dag = _load_dag_module().dag
        operator = dag.get_task("ingest_files_to_gcs")
        assert operator.preserve_folder_structure is True

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_operator_send_alert_is_true(self, _mock_var):
        dag = _load_dag_module().dag
        operator = dag.get_task("ingest_files_to_gcs")
        assert operator.send_alert is True

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_operator_connections_are_set(self, _mock_var):
        dag = _load_dag_module().dag
        operator = dag.get_task("ingest_files_to_gcs")
        assert operator.sharepoint_conn_id == "sharepoint_default"
        assert operator.gcs_conn_id == "google_cloud_default"


# ---------------------------------------------------------------------------
# Testes de default_args
# ---------------------------------------------------------------------------

class TestDefaultArgs:
    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_has_retry_configuration(self, _mock_var):
        dag = _load_dag_module().dag
        assert dag.default_args.get("retries") == 3

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_has_exponential_backoff(self, _mock_var):
        dag = _load_dag_module().dag
        assert dag.default_args.get("retry_exponential_backoff") is True

    @patch("airflow.models.Variable.get", side_effect=lambda key, default_var="": default_var)
    def test_dag_does_not_depend_on_past(self, _mock_var):
        dag = _load_dag_module().dag
        assert dag.default_args.get("depends_on_past") is False
