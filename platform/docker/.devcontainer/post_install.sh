#!/usr/bin/env bash
# post_install.sh -- runs inside the container after creation.
# Sets up shell history persistence, directories, and prints welcome info.
set -e

HOME_DIR="$HOME"

# ── Shell history persistence ──────────────────────────────────────────────
# The volume is mounted at ~/.shell_history. Point zsh and bash history there.
HISTORY_DIR="$HOME_DIR/.shell_history"
mkdir -p "$HISTORY_DIR"
touch "$HISTORY_DIR/.zsh_history"
touch "$HISTORY_DIR/.bash_history"

# Append history config to .zshrc if not already present
ZSHRC="$HOME_DIR/.zshrc"
if [ ! -f "$ZSHRC" ] || ! grep -q ".shell_history" "$ZSHRC" 2>/dev/null; then
  cat >> "$ZSHRC" << 'ZSHEOF'

# ── Persistent history (volume-backed) ──
HISTFILE="$HOME/.shell_history/.zsh_history"
HISTSIZE=10000
SAVEHIST=10000
setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_SPACE

# ── Aliases ──
alias ll='ls -la'
alias la='ls -A'
alias gs='git status'
alias gd='git diff'
alias start-openclaw='/opt/start-openclaw.sh'
ZSHEOF
fi

# Same for bash
BASHRC="$HOME_DIR/.bashrc"
if [ ! -f "$BASHRC" ] || ! grep -q ".shell_history" "$BASHRC" 2>/dev/null; then
  cat >> "$BASHRC" << 'BASHEOF'

# ── Persistent history (volume-backed) ──
HISTFILE="$HOME/.shell_history/.bash_history"
HISTSIZE=10000
HISTFILESIZE=10000
BASHEOF
fi

# ── Ensure OpenClaw directories exist ──────────────────────────────────────
mkdir -p "$HOME_DIR/.openclaw/data"
mkdir -p "$HOME_DIR/.openclaw/workspace"
mkdir -p "$HOME_DIR/.openclaw/config"

# ── SSH known hosts ────────────────────────────────────────────────────────
SSH_DIR="$HOME_DIR/.ssh"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
if [ ! -f "$SSH_DIR/known_hosts" ]; then
  ssh-keyscan github.com gitlab.com bitbucket.org > "$SSH_DIR/known_hosts" 2>/dev/null || true
  chmod 644 "$SSH_DIR/known_hosts" 2>/dev/null || true
fi

# ── Welcome message ───────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  OpenClaw Devcontainer Ready"
echo "=============================================="
echo ""
echo "  To start OpenClaw with Doppler secrets:"
echo "    start-openclaw"
echo ""
echo "  Or manually:"
echo "    doppler login"
echo "    doppler setup --project chat-force --config dev"
echo "    doppler run -- openclaw gateway --bind lan"
echo ""
echo "  Gateway will be available on port 3001."
echo ""
echo "=============================================="
echo ""
