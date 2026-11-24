FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install --yes --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pyspark==4.0.1 delta-spark==4.0.0
WORKDIR /opt/finops
ENV SPARK_LOCAL_IP=127.0.0.1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "analysis.run_delta"]
