#!/bin/bash
set -euo pipefail

: "${TASK_INSTRUCTION:?TASK_INSTRUCTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

OPENCLAW_DIR="/home/node/.openclaw"
WORKSPACE="/workspace/config"
GATEWAY_PORT=18789
SESSION_ID="worker-session-$$"
NEXT_MESSAGE_FILE="/tmp/next-message.txt"

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

# ── Helper: run a single OpenClaw turn and capture output ──
run_openclaw_turn() {
  local message="$1"
  local output_file
  output_file=$(mktemp /tmp/openclaw-turn-XXXXXX.json)

  echo "[Worker] Running OpenClaw turn..."
  openclaw agent \
    --agent main \
    --session-id "$SESSION_ID" \
    --message "$message" \
    --timeout "${AGENT_TIMEOUT:-1800}" \
    --json \
    > "$output_file" 2>&1 || true

  # Write latest response (overwritten each turn)
  cp "$output_file" /tmp/latest-response.json

  # Append to full session log
  cat "$output_file" >> /tmp/openclaw-output.json

  rm -f "$output_file"

  # Post-task cleanup: remove nested .git dirs from scaffolding tools
  find "$WORKSPACE" -mindepth 2 -name .git -type d -exec rm -rf {} + 2>/dev/null || true
}

signal_completion() {
  if [ -n "${ORCHESTRATOR_WEBHOOK_URL:-}" ]; then
    curl -sf -X POST "${ORCHESTRATOR_WEBHOOK_URL}/hooks/task-complete" \
      -H "Content-Type: application/json" \
      -d "{\"container_id\": \"$(hostname)\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"status\": \"complete\", \"session_id\": \"$SESSION_ID\"}" \
      || echo "[Worker] Warning: failed to notify orchestrator"
  fi
}

# ── 6. Run the initial task ──
echo "[Worker] Starting task: ${TASK_INSTRUCTION}"
run_openclaw_turn "$TASK_INSTRUCTION"
echo "[Worker] Task complete"
signal_completion

# ── 7. Message loop: wait for follow-up messages or shutdown ──
echo "[Worker] Waiting for messages or shutdown..."
while true; do
  # Check for next message file (written by orchestrator via docker cp)
  if [ -f "$NEXT_MESSAGE_FILE" ]; then
    MSG=$(cat "$NEXT_MESSAGE_FILE")
    rm -f "$NEXT_MESSAGE_FILE"

    echo "[Worker] Received follow-up message, processing..."
    run_openclaw_turn "$MSG"

    echo "[Worker] Turn complete"
    signal_completion
  fi

  # Check if Gateway is still alive
  if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
    echo "[Worker] Gateway died, exiting"
    exit 1
  fi

  sleep 2
done
