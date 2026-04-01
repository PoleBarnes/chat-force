#!/usr/bin/env bash
# provision.sh -- Provision a self-hosted OpenClaw devcontainer on macOS.
# -----------------------------------------------------------------------
# Runs on the HOST Mac (not inside a container). It:
#   1. Checks/installs prerequisites (OrbStack, devcontainer CLI, jq)
#   2. Creates a workspace directory with .devcontainer files
#   3. Starts the devcontainer via `devcontainer up`
#   4. Runs initial Doppler setup inside the container
#   5. Prints next steps
#
# Safe to re-run (idempotent). All persistent data lives in named Docker
# volumes, so the workspace directory can be recreated without data loss.
#
# Usage:
#   ./provision.sh                        # defaults to ~/.chat-force/openclaw
#   WORKSPACE=~/my/path ./provision.sh    # custom workspace location
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────

WORKSPACE="${WORKSPACE:-$HOME/.chat-force/openclaw}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEVCONTAINER_SRC="$SCRIPT_DIR/.devcontainer"
CONFIG_SRC="$SCRIPT_DIR/config"

# Colors for output (disable if not a terminal)
if [ -t 1 ]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' BOLD='' RESET=''
fi

info()  { echo -e "${BLUE}[info]${RESET}  $*"; }
ok()    { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error() { echo -e "${RED}[error]${RESET} $*"; }
step()  { echo -e "\n${BOLD}── $* ──${RESET}"; }

# ── Preflight: must be macOS ──────────────────────────────────────────────

if [ "$(uname -s)" != "Darwin" ]; then
  error "This script is intended for macOS. Detected: $(uname -s)"
  exit 1
fi

# ── Step 1: Check prerequisites ──────────────────────────────────────────

step "Checking prerequisites"

# OrbStack / Docker
if ! command -v docker &>/dev/null; then
  error "Docker CLI not found. Install OrbStack: https://orbstack.dev"
  exit 1
fi

if ! docker info &>/dev/null; then
  error "Docker daemon is not running. Start OrbStack first."
  exit 1
fi

# Check specifically for OrbStack (optional, just informational)
if docker info 2>/dev/null | grep -qi orbstack; then
  ok "OrbStack is running"
else
  warn "Docker is running but OrbStack not detected. Continuing anyway."
fi

# Node.js / npm (required for devcontainer CLI)
if ! command -v node &>/dev/null; then
  error "Node.js not found. Install it via: brew install node"
  exit 1
fi
ok "Node.js $(node --version)"

# devcontainer CLI
if ! command -v devcontainer &>/dev/null; then
  info "devcontainer CLI not found. Installing via npm..."
  npm install -g @devcontainers/cli
  if ! command -v devcontainer &>/dev/null; then
    error "Failed to install devcontainer CLI."
    error "Try manually: npm install -g @devcontainers/cli"
    exit 1
  fi
fi
ok "devcontainer CLI: $(devcontainer --version 2>/dev/null || echo 'installed')"

# jq
if ! command -v jq &>/dev/null; then
  info "jq not found. Installing via Homebrew..."
  if ! command -v brew &>/dev/null; then
    error "Homebrew not found. Install jq manually: brew install jq"
    exit 1
  fi
  brew install jq
fi
ok "jq: $(jq --version)"

# Doppler CLI (on the host -- optional, we mainly need it inside the container)
if command -v doppler &>/dev/null; then
  ok "Doppler CLI: $(doppler --version 2>/dev/null || echo 'installed')"
else
  warn "Doppler CLI not found on host (it is installed inside the container)."
  warn "If you want to run 'doppler run' on the host, install via: brew install dopplerhq/cli/doppler"
fi

# ── Step 2: Create workspace ─────────────────────────────────────────────

step "Setting up workspace at $WORKSPACE"

mkdir -p "$WORKSPACE"

# Copy .devcontainer files
if [ ! -d "$DEVCONTAINER_SRC" ]; then
  error "Cannot find .devcontainer source at: $DEVCONTAINER_SRC"
  error "Run this script from the repo: platform/docker/provision.sh"
  exit 1
fi

# Always sync .devcontainer files so updates are picked up on re-run
mkdir -p "$WORKSPACE/.devcontainer"
cp -f "$DEVCONTAINER_SRC/devcontainer.json" "$WORKSPACE/.devcontainer/"
cp -f "$DEVCONTAINER_SRC/Dockerfile"        "$WORKSPACE/.devcontainer/"
cp -f "$DEVCONTAINER_SRC/post_install.sh"   "$WORKSPACE/.devcontainer/"
cp -f "$DEVCONTAINER_SRC/start-openclaw.sh" "$WORKSPACE/.devcontainer/"
ok "Copied .devcontainer files"

# Copy config templates (for envsubst inside the container)
if [ -d "$CONFIG_SRC" ]; then
  mkdir -p "$WORKSPACE/platform/docker/config"
  cp -f "$CONFIG_SRC"/*.json "$WORKSPACE/platform/docker/config/" 2>/dev/null || true
  ok "Copied config templates"
fi

# Initialize a git repo to prevent parent repo detection by tools inside
if [ ! -d "$WORKSPACE/.git" ]; then
  git -C "$WORKSPACE" init --quiet
  # Create an initial commit so the repo is valid
  git -C "$WORKSPACE" commit --allow-empty -m "initial: openclaw workspace" --quiet
  ok "Initialized git repo in workspace"
else
  ok "Git repo already exists"
fi

# ── Step 3: Start the devcontainer ───────────────────────────────────────

step "Starting devcontainer"

info "This may take several minutes on first run (building image)..."

devcontainer up --workspace-folder "$WORKSPACE"

if [ $? -eq 0 ]; then
  ok "Devcontainer is running"
else
  error "Failed to start devcontainer. Check the output above."
  exit 1
fi

# ── Step 4: Doppler setup inside the container ───────────────────────────

step "Doppler setup (inside container)"

info "You will be prompted to log in to Doppler via your browser."
info ""

# Interactive login -- this needs a browser on the host and TTY passthrough
devcontainer exec --workspace-folder "$WORKSPACE" doppler login

if [ $? -eq 0 ]; then
  ok "Doppler login successful"
else
  warn "Doppler login was not completed. You can do it later inside the container:"
  warn "  devcontainer exec --workspace-folder $WORKSPACE doppler login"
fi

# Link the project non-interactively
devcontainer exec --workspace-folder "$WORKSPACE" \
  doppler setup --project chat-force --config dev --no-interactive

if [ $? -eq 0 ]; then
  ok "Doppler project linked: chat-force / dev"
else
  warn "Doppler project setup failed. Run inside the container:"
  warn "  doppler setup --project chat-force --config dev"
fi

# ── Step 5: Summary ──────────────────────────────────────────────────────

step "Provisioning complete"

echo ""
echo -e "${BOLD}Workspace:${RESET}  $WORKSPACE"
echo -e "${BOLD}Container:${RESET}  OpenClaw Self-Hosted"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo ""
echo "  1. Open a shell in the container:"
echo "     devcontainer exec --workspace-folder $WORKSPACE /bin/zsh"
echo ""
echo "  2. Start OpenClaw:"
echo "     start-openclaw"
echo "     # or: doppler run -- openclaw gateway --bind lan"
echo ""
echo "  3. The gateway will be available at:"
echo "     http://localhost:3001"
echo ""
echo "  To stop the container:"
echo "     docker stop \$(docker ps -qf label=devcontainer.local_folder=$WORKSPACE)"
echo ""
echo "  To re-provision (idempotent):"
echo "     $SCRIPT_DIR/provision.sh"
echo ""
