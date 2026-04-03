# Worker container — executes a single task in OpenClaw
# Config repo is CLONED inside (not mounted) so docker diff captures all changes
# OpenClaw workspace is symlinked to the repo so agent writes land in git-tracked space

FROM ghcr.io/openclaw/openclaw:latest

# git and curl are already in the base image; install anything else as root
USER root

# Create workspace directory and give node ownership
RUN mkdir -p /workspace/config && chown -R node:node /workspace

# Copy entrypoint (as root so it's owned by root and not writable by node)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to node for everything else
USER node

# Clone the config repo at build time
ARG CONFIG_REPO_URL
ARG CONFIG_BRANCH=main
RUN git clone --depth 1 --branch ${CONFIG_BRANCH} ${CONFIG_REPO_URL} /workspace/config

# Copy workspace identity files (SOUL, IDENTITY, etc.) into repo root
# so they're at the top level of the workspace the agent sees
RUN cp /workspace/config/docker/config/workspace/*.md /workspace/config/ 2>/dev/null || true

# Point OpenClaw's workspace at the git repo
# This is the key: agent file writes land inside the tracked repo
RUN mkdir -p /home/node/.openclaw && \
    rm -rf /home/node/.openclaw/workspace && \
    ln -s /workspace/config /home/node/.openclaw/workspace

# Install the afterTurn hook
COPY --chown=node:node hooks/notify-orchestrator/ /home/node/.openclaw/hooks/notify-orchestrator/

# The orchestrator sets these at runtime:
#   TASK_INSTRUCTION — what to do
#   ORCHESTRATOR_WEBHOOK_URL — where to POST afterTurn
#   ANTHROPIC_AUTH_TOKEN — LLM access

ENTRYPOINT ["/entrypoint.sh"]
