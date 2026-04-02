# Mechanic container — evaluates changesets from the Worker
# Read-only access to changeset, writes verdict to /output

FROM ghcr.io/openclaw/openclaw:latest

# Install gh CLI for PR creation support
RUN apt-get update && apt-get install -y gh git && rm -rf /var/lib/apt/lists/*

# Copy Mechanic workspace config
COPY config/SOUL.md /home/node/.openclaw/workspace/SOUL.md
COPY config/IDENTITY.md /home/node/.openclaw/workspace/IDENTITY.md
COPY config/AGENTS.md /home/node/.openclaw/workspace/AGENTS.md

# The orchestrator mounts at runtime:
#   /changeset:ro — the changeset bundle from the Worker
#   /output       — where the Mechanic writes its verdict

# Env vars set at runtime:
#   TASK_DESCRIPTION — what the Worker was asked to do
#   ANTHROPIC_AUTH_TOKEN — LLM access

ENTRYPOINT ["openclaw", "agent", "--agent", "main"]
