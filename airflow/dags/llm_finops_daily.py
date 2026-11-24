from datetime import timedelta

import pendulum
from airflow.decorators import dag
from airflow.operators.bash import BashOperator

VENV = "/home/airflow/finops-venv/bin"
PYTHON = f"{VENV}/python"
DBT = f"{VENV}/dbt --no-use-colors"
WAREHOUSE = f"{PYTHON} -m ingestion.warehouse"
ROOT = "/opt/finops"


@dag(
    dag_id="llm_finops_daily",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=3)},
    tags=["finops", "warehouse"],
)
def daily():
    def run(task_id, command, **env):
        return BashOperator(
            task_id=task_id, bash_command=command, cwd=ROOT,
            env={"DBT_PROJECT_DIR": f"{ROOT}/dbt_project",
                 "DBT_PROFILES_DIR": f"{ROOT}/dbt_project", **env},
            append_env=True,
        )

    extract = run("extract", f"{PYTHON} -m ingestion.fetch_open_models --hf-limit 100")
    validate = run("validate", f"{WAREHOUSE} prepare")
    load = run("load_bronze", f'{WAREHOUSE} load "$BATCH_PATH"',
               BATCH_PATH="{{ ti.xcom_pull(task_ids='validate') }}")
    models = run("dbt_run", f"{DBT} snapshot && {DBT} run")
    test = run("dbt_test", f"{DBT} test && {WAREHOUSE} grant-bi")
    extract >> validate >> load >> models >> test


daily()
