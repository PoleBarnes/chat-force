#!/usr/bin/env bash
# start-openclaw.sh -- Starts the OpenClaw gateway with Doppler secrets.
# Run this inside the devcontainer (manually or via tmux).
#
# It ensures Doppler is authenticated and the project is linked, then
# substitutes config templates with real secret values and launches the
# gateway.
set -e

CONFIG_DIR="$HOME/.openclaw"
TEMPLATE_DIR="/workspace/platform/docker/config"

# ── Check Doppler authentication ──────────────────────────────────────────
if ! doppler me &>/dev/null; then
  echo ""
  echo "Doppler is not authenticated. Starting interactive login..."
  echo "(This will open a browser on your host machine.)"
  echo ""
  doppler login
fi

echo "Doppler auth: OK ($(doppler me --json 2>/dev/null | jq -r '.name // "authenticated"'))"

# ── Check project is linked ───────────────────────────────────────────────
if ! doppler secrets --only-names &>/dev/null; then
  echo ""
  echo "Linking Doppler project..."
  doppler setup --project chat-force --config dev
fi

echo "Doppler project: chat-force / dev"

# ── Verify required secrets exist ─────────────────────────────────────────
echo ""
echo "Verifying required secrets..."

REQUIRED_SECRETS="SLACK_BOT_TOKEN SLACK_APP_TOKEN ANTHROPIC_AUTH_TOKEN"
MISSING=""

for secret in $REQUIRED_SECRETS; do
  if doppler secrets get "$secret" --plain &>/dev/null; then
    echo "  [ok] $secret"
  else
    MISSING="$MISSING $secret"
    echo "  [MISSING] $secret"
  fi
done

if [ -n "$MISSING" ]; then
  echo ""
  echo "ERROR: Missing required secrets:$MISSING"
  echo "Add them in the Doppler dashboard or with:"
  echo "  doppler secrets set SECRET_NAME=value"
  exit 1
fi

# ── Substitute config templates ───────────────────────────────────────────
# Use Doppler to export secrets as env vars, then envsubst to fill templates.
echo ""
echo "Generating config files from templates..."

mkdir -p "$CONFIG_DIR"

if [ -d "$TEMPLATE_DIR" ]; then
  for template in "$TEMPLATE_DIR"/*.json; do
    [ -f "$template" ] || continue
    filename="$(basename "$template")"
    # Run envsubst with the secrets from Doppler injected into the environment
    doppler run -- bash -c "envsubst < '$template'" > "$CONFIG_DIR/$filename"
    echo "  $filename -> $CONFIG_DIR/$filename"
  done
else
  echo "  (no templates found at $TEMPLATE_DIR, skipping)"
fi

# ── Copy auth-profiles to agent directory ─────────────────────────────────
# OpenClaw agents read auth from their own directory, not the root config
AGENT_AUTH_DIR="$CONFIG_DIR/agents/main/agent"
mkdir -p "$AGENT_AUTH_DIR"
if [ -f "$CONFIG_DIR/auth-profiles.json" ]; then
  cp "$CONFIG_DIR/auth-profiles.json" "$AGENT_AUTH_DIR/auth-profiles.json"
  echo "  auth-profiles.json -> $AGENT_AUTH_DIR/auth-profiles.json"
fi

# ── Start OpenClaw gateway ────────────────────────────────────────────────
echo ""
echo "Starting OpenClaw gateway on port 3001..."
echo "Press Ctrl+C to stop."
echo ""

exec doppler run -- openclaw gateway --bind lan
