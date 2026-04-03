#!/bin/bash
set -euo pipefail

: "${TASK_INSTRUCTION:?TASK_INSTRUCTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

OPENCLAW_DIR="/home/node/.openclaw"
WORKSPACE="/workspace/config"
GATEWAY_PORT=18789
SESSION_ID="worker-session-$$"

echo "[Worker] Configuring OpenClaw..."

# ── 1. Write minimal openclaw.json ──
cat > "$OPENCLAW_DIR/openclaw.json" <<CONF
{
  "agents": {
    "defaults": {
      "workspace": "$WORKSPACE",
      "model": {
        "primary": "anthropic/claude-opus-4-6"
      }
    }
  },
  "gateway": {
    "port": $GATEWAY_PORT,
    "mode": "local",
    "bind": "loopback",
    "auth": {
      "mode": "none"
    }
  },
  "tools": {
    "profile": "full",
    "exec": {
      "security": "full"
    },
    "elevated": {
      "enabled": true
    }
  }
}
CONF

# ── 2. Write auth profile ──
mkdir -p "$OPENCLAW_DIR/agents/main/agent"
cat > "$OPENCLAW_DIR/agents/main/agent/auth-profiles.json" <<AUTH
{
  "profiles": {
    "anthropic:default": {
      "provider": "anthropic",
      "type": "api_key",
      "key": "$ANTHROPIC_AUTH_TOKEN"
    }
  }
}
AUTH
cp "$OPENCLAW_DIR/agents/main/agent/auth-profiles.json" "$OPENCLAW_DIR/auth-profiles.json"

# ── 3. Set up git baseline ──
cd "$WORKSPACE"
git config user.name "Worker"
git config user.email "worker@chat-force.local"
echo ".openclaw/" >> .gitignore
echo "HEARTBEAT.md" >> .gitignore
git add -A
git commit -m "baseline" --allow-empty

# ── 4. Start the Gateway ──
echo "[Worker] Starting OpenClaw Gateway on port $GATEWAY_PORT..."
openclaw gateway run --port "$GATEWAY_PORT" --bind loopback --force &
GATEWAY_PID=$!

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$GATEWAY_PORT/health" 2>/dev/null | grep -q '"ok":true'; then
    echo "[Worker] Gateway is ready"
    break
  fi
  if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
    echo "[Worker] ERROR: Gateway process died"
    exit 1
  fi
  sleep 1
done

# ── 5. Auto-approve all exec ──
openclaw approvals allowlist add --agent "*" "**" 2>/dev/null || true

# ── 6. Run the initial task ──
echo "[Worker] Starting task: ${TASK_INSTRUCTION}"
openclaw agent \
  --agent main \
  --session-id "$SESSION_ID" \
  --message "${TASK_INSTRUCTION}" \
  --timeout "${AGENT_TIMEOUT:-1800}" \
  --json \
  > /tmp/openclaw-output.json 2>&1 || true

# Post-task cleanup: remove nested .git dirs from scaffolding tools
find "$WORKSPACE" -mindepth 2 -name .git -type d -exec rm -rf {} + 2>/dev/null || true

echo "[Worker] Task complete"

# ── 7. Signal completion and wait for possible feedback ──
# The orchestrator may send feedback via FEEDBACK_FILE, or stop the container.
FEEDBACK_FILE="/tmp/mechanic-feedback.txt"

signal_completion() {
  if [ -n "${ORCHESTRATOR_WEBHOOK_URL:-}" ]; then
    curl -sf -X POST "${ORCHESTRATOR_WEBHOOK_URL}/hooks/task-complete" \
      -H "Content-Type: application/json" \
      -d "{\"container_id\": \"$(hostname)\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"status\": \"complete\", \"session_id\": \"$SESSION_ID\"}" \
      || echo "[Worker] Warning: failed to notify orchestrator"
  fi
}

signal_completion

# ── 8. Feedback loop: wait for feedback, iterate, signal again ──
echo "[Worker] Waiting for feedback or shutdown..."
while true; do
  # Check for feedback file (written by orchestrator via docker cp)
  if [ -f "$FEEDBACK_FILE" ]; then
    FEEDBACK=$(cat "$FEEDBACK_FILE")
    rm -f "$FEEDBACK_FILE"

    echo "[Worker] Received feedback, iterating..."
    openclaw agent \
      --agent main \
      --session-id "$SESSION_ID" \
      --message "$FEEDBACK" \
      --timeout "${AGENT_TIMEOUT:-1800}" \
      --json \
      >> /tmp/openclaw-output.json 2>&1 || true

    # Post-task cleanup
    find "$WORKSPACE" -mindepth 2 -name .git -type d -exec rm -rf {} + 2>/dev/null || true

    echo "[Worker] Iteration complete"
    signal_completion
  fi

  # Check if Gateway is still alive
  if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
    echo "[Worker] Gateway died, exiting"
    exit 1
  fi

  sleep 2
done
