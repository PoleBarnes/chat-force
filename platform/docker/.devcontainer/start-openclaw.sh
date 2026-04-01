#!/usr/bin/env bash
# start-openclaw.sh -- Starts the OpenClaw gateway with Doppler secrets.
# Run this inside the devcontainer (manually or via tmux).
#
# It ensures Doppler is authenticated and the project is linked, then
# substitutes config templates with real secret values and launches the
# gateway.
set -e

CONFIG_DIR="/home/node/.openclaw"
TEMPLATE_DIR="/workspace/platform/docker/config"
DOPPLER_ENV_FILE="$CONFIG_DIR/.env.doppler"

# ── Load Doppler service token ────────────────────────────────────────────
# The service token is injected by provision.sh — no interactive login needed.
if [ -z "${DOPPLER_TOKEN:-}" ] && [ -f "$DOPPLER_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$DOPPLER_ENV_FILE"
  export DOPPLER_TOKEN
fi

if [ -z "${DOPPLER_TOKEN:-}" ]; then
  echo ""
  echo "ERROR: No Doppler service token found."
  echo "Re-run provision.sh on your Mac to set up Doppler."
  exit 1
fi

# Verify the token works
if ! doppler secrets --only-names &>/dev/null 2>&1; then
  echo ""
  echo "ERROR: Doppler service token is invalid or expired."
  echo "Re-run provision.sh on your Mac to create a new one."
  exit 1
fi

echo "Doppler: OK (service token)"

# ── Verify required secrets exist ─────────────────────────────────────────
echo ""
echo "Verifying required secrets..."

REQUIRED_SECRETS="SLACK_BOT_TOKEN SLACK_APP_TOKEN ANTHROPIC_AUTH_TOKEN GEMINI_API_KEY"
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

# ── Pre-create directory structure ────────────────────────────────────────
mkdir -p "$CONFIG_DIR/agents/main/agent"
mkdir -p "$CONFIG_DIR/agents/main/sessions"
mkdir -p "$CONFIG_DIR/identity"

# ── Substitute config templates ───────────────────────────────────────────
# Use Doppler to export secrets as env vars, then envsubst to fill templates.
echo ""
echo "Generating config files from templates..."

if [ -d "$TEMPLATE_DIR" ]; then
  for template in "$TEMPLATE_DIR"/*.json; do
    [ -f "$template" ] || continue
    filename="$(basename "$template")"
    doppler run -- bash -c "envsubst < '$template'" > "$CONFIG_DIR/$filename"
    echo "  $filename -> $CONFIG_DIR/$filename"
  done
else
  echo "  (no templates found at $TEMPLATE_DIR, skipping)"
fi

# ── Copy auth-profiles to agent directory ─────────────────────────────────
# OpenClaw reads auth from both the root config dir and each agent's directory.
AGENT_AUTH_DIR="$CONFIG_DIR/agents/main/agent"
if [ -f "$CONFIG_DIR/auth-profiles.json" ]; then
  cp "$CONFIG_DIR/auth-profiles.json" "$AGENT_AUTH_DIR/auth-profiles.json"
  echo "  auth-profiles.json -> $AGENT_AUTH_DIR/auth-profiles.json"
fi

# ── Start OpenClaw gateway ────────────────────────────────────────────────
echo ""
echo "Starting OpenClaw gateway on port 18789..."
echo "Press Ctrl+C to stop."
echo ""

exec doppler run -- openclaw gateway --bind lan --port 18789
