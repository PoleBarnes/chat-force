#!/bin/bash
set -euo pipefail

: "${TASK_INSTRUCTION:?TASK_INSTRUCTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

OPENCLAW_DIR="/home/node/.openclaw"
WORKSPACE="/workspace/config"
GATEWAY_PORT=18789

echo "[Worker] Configuring OpenClaw..."

# ── 1. Write minimal openclaw.json (no channels, just gateway + model) ──
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
    }
  }
}
CONF

# ── 2. Write auth profile (Anthropic API key from env) ──
# OpenClaw looks for auth in the per-agent directory, not the top-level.
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
# Also write to top-level as fallback
cp "$OPENCLAW_DIR/agents/main/agent/auth-profiles.json" "$OPENCLAW_DIR/auth-profiles.json"

# ── 3. Auto-approve all exec for headless operation ──
# Done after Gateway starts (the CLI needs the Gateway running).

# ── 4. Set up git baseline ──
cd "$WORKSPACE"
git config user.name "Worker"
git config user.email "worker@chat-force.local"
# Ignore OpenClaw runtime artifacts
echo ".openclaw/" >> .gitignore
echo "HEARTBEAT.md" >> .gitignore
git add -A
git commit -m "baseline" --allow-empty

# ── 5. Start the Gateway in the background ──
echo "[Worker] Starting OpenClaw Gateway on port $GATEWAY_PORT..."
openclaw gateway run --port "$GATEWAY_PORT" --bind loopback --force &
GATEWAY_PID=$!

# Wait for Gateway to be ready (HTTP health endpoint)
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

# ── 6. Auto-approve all exec (disposable sandbox, no human in the loop) ──
openclaw approvals allowlist add --agent "*" "**" 2>/dev/null || true

# ── 7. Run the task ──
echo "[Worker] Starting task: ${TASK_INSTRUCTION}"
openclaw agent \
  --agent main \
  --message "${TASK_INSTRUCTION}" \
  --timeout "${AGENT_TIMEOUT:-1800}" \
  --json \
  > /tmp/openclaw-output.json 2>&1 || true

echo "[Worker] Task complete"

# ── 8. Signal completion to orchestrator ──
if [ -n "${ORCHESTRATOR_WEBHOOK_URL:-}" ]; then
  curl -sf -X POST "${ORCHESTRATOR_WEBHOOK_URL}/hooks/task-complete" \
    -H "Content-Type: application/json" \
    -d "{\"container_id\": \"$(hostname)\", \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"status\": \"complete\"}" \
    || echo "[Worker] Warning: failed to notify orchestrator"
fi

# ── 9. Keep alive for changeset extraction ──
echo "[Worker] Waiting for orchestrator to extract changeset..."
wait "$GATEWAY_PID" 2>/dev/null || sleep infinity
