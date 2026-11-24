FROM apache/airflow:2.10.5-python3.11
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock /tmp/finops-deps/
ENV UV_PROJECT_ENVIRONMENT=/home/airflow/finops-venv UV_LINK_MODE=copy
RUN uv sync --project /tmp/finops-deps --locked --no-install-project
