#!/usr/bin/env bash
# post_install.sh -- runs inside the container after creation.
# Sets up directory structure and prints welcome info.
set -e

HOME_DIR="/home/node"

# ── Fix volume ownership (Docker volumes default to root) ────────────────
# Named volumes mount as root:root. Fix ownership so node user can write.
for dir in "$HOME_DIR/.openclaw" "$HOME_DIR/.doppler"; do
  if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    echo "Fixing ownership: $dir"
    sudo chown -R node:node "$dir"
  fi
done

# ── Ensure OpenClaw directory structure exists ────────────────────────────
mkdir -p "$HOME_DIR/.openclaw/agents/main/agent"
mkdir -p "$HOME_DIR/.openclaw/agents/main/sessions"
mkdir -p "$HOME_DIR/.openclaw/identity"
mkdir -p "$HOME_DIR/.openclaw/workspace"
mkdir -p "$HOME_DIR/.doppler"

# ── SSH known hosts ───────────────────────────────────────────────────────
SSH_DIR="$HOME_DIR/.ssh"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
if [ ! -f "$SSH_DIR/known_hosts" ]; then
  ssh-keyscan github.com gitlab.com bitbucket.org > "$SSH_DIR/known_hosts" 2>/dev/null || true
  chmod 644 "$SSH_DIR/known_hosts" 2>/dev/null || true
fi

# ── Welcome message ──────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  OpenClaw Devcontainer Ready"
echo "=============================================="
echo ""
echo "  To start OpenClaw with Doppler secrets:"
echo "    /opt/start-openclaw.sh"
echo ""
echo "  Or manually:"
echo "    doppler login"
echo "    doppler setup --project chat-force --config dev"
echo "    doppler run -- openclaw gateway --bind lan --port 18789"
echo ""
echo "  Gateway will be available on port 18789."
echo ""
echo "=============================================="
echo ""
