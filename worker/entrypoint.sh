#!/bin/bash
set -euo pipefail

# Validate required env vars
: "${TASK_INSTRUCTION:?TASK_INSTRUCTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

# OpenClaw --local mode reads ANTHROPIC_API_KEY from the environment
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN}"

echo "[Worker] Starting OpenClaw with task: ${TASK_INSTRUCTION}"

# Initialize git baseline.
# The Dockerfile COPYs the repo and workspace files into /workspace/config.
# We commit that state plus gitignore rules for OpenClaw runtime artifacts
# so only real agent output shows up in the changeset diff.
cd /workspace/config
git config user.name "Worker"
git config user.email "worker@chat-force.local"
echo ".openclaw/" >> .gitignore
echo "HEARTBEAT.md" >> .gitignore
git add -A
git commit -m "baseline" --allow-empty

# Run the task via OpenClaw CLI (--local mode, no Gateway needed)
openclaw agent \
  --local \
  --agent main \
  --message "${TASK_INSTRUCTION}" \
  --json \
  > /tmp/openclaw-output.json 2>&1 || true

echo "[Worker] OpenClaw execution complete"

# Signal explicit completion to orchestrator
if [ -n "${ORCHESTRATOR_WEBHOOK_URL:-}" ]; then
  curl -sf -X POST "${ORCHESTRATOR_WEBHOOK_URL}/hooks/task-complete" \
    -H "Content-Type: application/json" \
    -d "{\"container_id\": \"$(hostname)\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"status\": \"complete\"}" \
    || echo "[Worker] Warning: failed to notify orchestrator"
fi

# Keep container alive for changeset extraction
echo "[Worker] Waiting for orchestrator to extract changeset..."
sleep infinity
