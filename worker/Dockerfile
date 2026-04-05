FROM python:3.13-slim

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/sh worker \
    && mkdir -p /app /harness /tmp \
    && chown -R worker:worker /harness \
    && chmod 1777 /tmp

RUN pip install --no-cache-dir claude-agent-sdk

COPY worker/entrypoint.py /app/entrypoint.py

USER worker

WORKDIR /harness

ENTRYPOINT ["python", "/app/entrypoint.py"]
