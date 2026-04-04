FROM python:3.13-slim

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/sh worker \
    && mkdir -p /app /workspace/config /tmp \
    && chown -R worker:worker /workspace/config \
    && chmod 1777 /tmp

RUN pip install --no-cache-dir claude-agent-sdk

COPY worker/entrypoint.py /app/entrypoint.py

COPY --chown=worker:worker . /workspace/config
COPY --chown=worker:worker docker/config/workspace/SOUL.md /workspace/config/SOUL.md
COPY --chown=worker:worker docker/config/workspace/IDENTITY.md /workspace/config/IDENTITY.md
COPY --chown=worker:worker docker/config/workspace/USER.md /workspace/config/USER.md
COPY --chown=worker:worker docker/config/workspace/AGENTS.md /workspace/config/AGENTS.md

RUN git -C /workspace/config init \
    && git -C /workspace/config config user.name "worker" \
    && git -C /workspace/config config user.email "worker@local" \
    && git -C /workspace/config add . \
    && git -C /workspace/config commit -m "baseline" \
    && chown -R worker:worker /workspace/config

USER worker

WORKDIR /workspace/config

ENTRYPOINT ["python", "/app/entrypoint.py"]
