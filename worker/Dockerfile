# Worker container — executes a single task in OpenClaw
# Config repo is CLONED inside (not mounted) so docker diff captures all changes

FROM ghcr.io/openclaw/openclaw:latest

# Install git (needed for changeset extraction via exec)
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Clone the config repo at build time
ARG CONFIG_REPO_URL
ARG CONFIG_BRANCH=main
RUN git clone --depth 1 --branch ${CONFIG_BRANCH} ${CONFIG_REPO_URL} /workspace/config

# Copy workspace files into OpenClaw's expected location
RUN cp /workspace/config/docker/config/workspace/*.md /home/node/.openclaw/workspace/ 2>/dev/null || true

# Copy skills
RUN mkdir -p /home/node/.openclaw/workspace/skills && \
    cp /workspace/config/skills/*.md /home/node/.openclaw/workspace/skills/ 2>/dev/null || true

# Install the afterTurn hook
COPY hooks/notify-orchestrator/ /home/node/.openclaw/hooks/notify-orchestrator/

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# The orchestrator sets these at runtime:
#   TASK_INSTRUCTION — what to do
#   ORCHESTRATOR_WEBHOOK_URL — where to POST afterTurn
#   ANTHROPIC_AUTH_TOKEN — LLM access

ENTRYPOINT ["/entrypoint.sh"]
