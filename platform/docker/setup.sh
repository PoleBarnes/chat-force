#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "=== OpenClaw Docker Setup (Doppler) ==="
echo ""

# ── Check that Doppler CLI is installed ─────────────────────────────────────

if ! command -v doppler &>/dev/null; then
  echo "Doppler CLI not found. Installing..."
  curl -sLf --retry 3 --tlsv1.2 --proto "=https" "https://cli.doppler.com/install.sh" | sudo sh
  if ! command -v doppler &>/dev/null; then
    echo "ERROR: Doppler CLI installation failed."
    echo "Try manually: https://docs.doppler.com/docs/install-cli"
    exit 1
  fi
fi

echo "Doppler CLI found: $(doppler --version)"

# ── Check that the user is logged in ────────────────────────────────────────

if ! doppler me &>/dev/null; then
  echo ""
  echo "ERROR: You are not logged in to Doppler."
  echo ""
  echo "Run:"
  echo "  doppler login"
  exit 1
fi

echo "Doppler auth OK: $(doppler me --json 2>/dev/null | grep -o '"name":"[^"]*"' | head -1)"

# ── Link this directory to the Doppler project ──────────────────────────────

echo ""
echo "Linking directory to Doppler project 'chat-force' (config: dev)..."
echo ""

doppler setup --project chat-force --config dev --no-interactive

echo ""
echo "Doppler project linked."

# ── Verify required secrets exist ───────────────────────────────────────────

echo ""
echo "Verifying required secrets..."

REQUIRED_SECRETS="SLACK_BOT_TOKEN SLACK_APP_TOKEN ANTHROPIC_AUTH_TOKEN"
MISSING=""

SECRET_NAMES=$(doppler secrets --only-names --plain --no-interactive 2>/dev/null)

for secret in $REQUIRED_SECRETS; do
  if echo "$SECRET_NAMES" | grep -qx "$secret"; then
    echo "  $secret"
  else
    MISSING="$MISSING $secret"
  fi
done

if [ -n "$MISSING" ]; then
  echo ""
  echo "ERROR: The following secrets are missing from Doppler:"
  for m in $MISSING; do
    echo "  - $m"
  done
  echo ""
  echo "Add them in the Doppler dashboard or with:"
  echo "  doppler secrets set SECRET_NAME=value"
  exit 1
fi

echo ""
echo "All required secrets are present."

# ── Clean up legacy .env if present ─────────────────────────────────────────

if [ -f "$SCRIPT_DIR/.env" ]; then
  echo ""
  echo "WARNING: A legacy .env file exists at $SCRIPT_DIR/.env"
  echo "         Doppler now manages secrets. You can safely remove it:"
  echo "         rm $SCRIPT_DIR/.env"
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo "=== Setup complete ==="
echo ""
echo "Start the gateway with:"
echo "  cd $(basename "$SCRIPT_DIR") && doppler run -- docker compose up -d"
echo ""
