# Mechanic container — evaluates changesets from the Worker
# Read-only access to changeset, writes verdict to /output

FROM ghcr.io/openclaw/openclaw:latest

USER root

# Create workspace and output directories
RUN mkdir -p /home/node/.openclaw/workspace /output && \
    chown -R node:node /home/node/.openclaw /output

# Copy entrypoint
COPY mechanic/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER node

# Copy Mechanic workspace config
COPY --chown=node:node mechanic/config/SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY --chown=node:node mechanic/config/IDENTITY.md /home/node/.openclaw/workspace/IDENTITY.md
COPY --chown=node:node mechanic/config/AGENTS.md /home/node/.openclaw/workspace/AGENTS.md

# The orchestrator mounts at runtime:
#   /changeset:ro — the changeset bundle from the Worker
#   /output       — where the Mechanic writes its verdict

ENTRYPOINT ["/entrypoint.sh"]
