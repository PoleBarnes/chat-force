# Worker container — a disposable OpenClaw instance that executes a single task.
# Runs the full Gateway internally so the agent has shell, file, and web tools.
# The repo is COPYed from the build context so docker diff captures all changes.

FROM ghcr.io/openclaw/openclaw:latest

USER root

# Create directories the entrypoint needs.
# /workspace is owned by root so the agent can't write outside /workspace/config.
RUN mkdir -p /workspace/config /home/node/.openclaw && \
    chown -R node:node /workspace/config /home/node/.openclaw

# Copy entrypoint
COPY worker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER node

# Copy the repo from the build context
COPY --chown=node:node . /workspace/config

# Copy workspace identity files (SOUL, IDENTITY, etc.) into repo root
RUN cp /workspace/config/docker/config/workspace/*.md /workspace/config/ 2>/dev/null || true

# Point OpenClaw's workspace at the git repo
RUN ln -s /workspace/config /home/node/.openclaw/workspace

# Install the afterTurn hook
COPY --chown=node:node worker/hooks/notify-orchestrator/ /home/node/.openclaw/hooks/notify-orchestrator/

ENTRYPOINT ["/entrypoint.sh"]
