# Worker container — executes a single task in OpenClaw
# The repo is COPYed from the build context (not cloned from GitHub)
# so docker diff captures all changes the agent makes.

FROM ghcr.io/openclaw/openclaw:latest

USER root

# Create workspace directory and give node ownership
RUN mkdir -p /workspace/config /home/node/.openclaw && \
    chown -R node:node /workspace /home/node/.openclaw

# Copy entrypoint (as root so it's owned by root and not writable by node)
COPY worker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER node

# Copy the repo from the build context (the repo root)
# This avoids cloning from GitHub and leaking tokens in image layers
COPY --chown=node:node . /workspace/config

# Copy workspace identity files (SOUL, IDENTITY, etc.) into repo root
# so they're at the top level of the workspace the agent sees
RUN cp /workspace/config/docker/config/workspace/*.md /workspace/config/ 2>/dev/null || true

# Point OpenClaw's workspace at the git repo
# Agent file writes land inside the tracked repo
RUN ln -s /workspace/config /home/node/.openclaw/workspace

# Install the afterTurn hook
COPY --chown=node:node worker/hooks/notify-orchestrator/ /home/node/.openclaw/hooks/notify-orchestrator/

ENTRYPOINT ["/entrypoint.sh"]
