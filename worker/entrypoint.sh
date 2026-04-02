#!/bin/bash
set -euo pipefail

# Validate required env vars
: "${TASK_INSTRUCTION:?TASK_INSTRUCTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

echo "[Worker] Starting OpenClaw with task: ${TASK_INSTRUCTION}"

# Initialize git in the config directory so we can diff later
cd /workspace/config
git add -A
git commit -m "baseline" --allow-empty 2>/dev/null || true

# Run the task via OpenClaw CLI
openclaw agent \
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
