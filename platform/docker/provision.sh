#!/usr/bin/env bash
# provision.sh -- Provision a self-hosted OpenClaw devcontainer on macOS.
# -----------------------------------------------------------------------
# Runs on the HOST Mac (not inside a container). It:
#   1. Checks/installs prerequisites (OrbStack, devcontainer CLI, jq)
#   2. Creates a workspace directory with .devcontainer files
#   3. Starts the devcontainer via `devcontainer up`
#   4. Creates a Doppler service token (one-time, cached across --clean)
#   5. Runs OpenAI Codex OAuth onboard
#   6. Prints next steps
#
# Safe to re-run (idempotent). All persistent data lives in named Docker
# volumes, so the workspace directory can be recreated without data loss.
#
# Usage:
#   ./provision.sh                        # normal provision (idempotent)
#   ./provision.sh --clean                # stop + remove container and volumes, then provision fresh
#   ./provision.sh --destroy              # tear everything down (container, volumes, workspace) and exit
#   WORKSPACE=~/my/path ./provision.sh    # custom workspace location
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────

WORKSPACE="${WORKSPACE:-$HOME/.chat-force/openclaw}"
CLEAN=false
DESTROY=false

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --clean)   CLEAN=true ;;
    --destroy) DESTROY=true ;;
    --help|-h)
      echo "Usage: ./provision.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --clean     Remove container and volumes, then re-provision from scratch"
      echo "  --destroy   Remove container, volumes, and workspace directory, then exit"
      echo "  --help      Show this help"
      echo ""
      echo "Environment:"
      echo "  WORKSPACE   Workspace path (default: ~/.chat-force/openclaw)"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)"
      exit 1
      ;;
  esac
done

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

# ── Teardown (--clean or --destroy) ──────────────────────────────────────

if $CLEAN || $DESTROY; then
  step "Tearing down existing environment"

  # Stop and remove the container
  CID=$(docker ps -aqf "label=devcontainer.local_folder=$WORKSPACE" 2>/dev/null || true)
  if [ -n "$CID" ]; then
    info "Stopping container $CID..."
    docker stop "$CID" 2>/dev/null || true
    docker rm "$CID" 2>/dev/null || true
    ok "Container removed"
  else
    info "No container found for $WORKSPACE"
  fi

  # Remove associated volumes (doppler is a bind mount, not a volume)
  VOLUMES=$(docker volume ls -q 2>/dev/null | grep -E "openclaw" || true)
  if [ -n "$VOLUMES" ]; then
    info "Removing volumes..."
    echo "$VOLUMES" | xargs docker volume rm 2>/dev/null || true
    ok "Volumes removed"
  else
    info "No matching volumes found"
  fi

  # Remove the built image (forces rebuild on next provision)
  IMAGE=$(docker images -q --filter "label=devcontainer.local_folder=$WORKSPACE" 2>/dev/null || true)
  if [ -n "$IMAGE" ]; then
    info "Removing devcontainer image..."
    docker rmi "$IMAGE" 2>/dev/null || true
    ok "Image removed"
  fi

  if $DESTROY; then
    # Also remove the workspace directory
    if [ -d "$WORKSPACE" ]; then
      info "Removing workspace directory: $WORKSPACE"
      rm -rf "$WORKSPACE"
      ok "Workspace removed"
    fi
    echo ""
    ok "Full teardown complete. Nothing left."
    exit 0
  fi

  ok "Teardown complete — continuing with fresh provision..."
fi

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
if docker context show 2>/dev/null | grep -qi orbstack || docker info 2>&1 | grep -qi orbstack; then
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


# ── Step 2: Create workspace ─────────────────────────────────────────────

step "Setting up workspace at $WORKSPACE"

mkdir -p "$WORKSPACE"

# Doppler service token cache (persists across --clean provisions)
DOPPLER_TOKEN_FILE="$WORKSPACE/.doppler-service-token"

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
  echo ".doppler-service-token" > "$WORKSPACE/.gitignore"
  git -C "$WORKSPACE" add .gitignore
  git -C "$WORKSPACE" commit --allow-empty -m "initial: openclaw workspace" --quiet
  ok "Initialized git repo in workspace"
else
  # Ensure gitignore is up to date
  grep -qxF '.doppler-service-token' "$WORKSPACE/.gitignore" 2>/dev/null \
    || echo ".doppler-service-token" >> "$WORKSPACE/.gitignore"
  ok "Git repo already exists"
fi

# ── Step 3: Start the devcontainer ───────────────────────────────────────

step "Starting devcontainer"

info "This may take a minute on first run (pulling official image + adding Doppler)..."

if devcontainer up --workspace-folder "$WORKSPACE"; then
  ok "Devcontainer is running"
else
  error "Failed to start devcontainer. Check the output above."
  exit 1
fi

# ── Step 3b: Fix Docker volume permissions ───────────────────────────────

step "Fixing volume permissions"

CONTAINER_ID=$(docker ps -qf "label=devcontainer.local_folder=$WORKSPACE")
if [ -n "$CONTAINER_ID" ]; then
  docker exec -u root "$CONTAINER_ID" chown -R node:node /home/node/.openclaw /home/node/.doppler 2>/dev/null || true
  ok "Volume permissions fixed"
else
  warn "Container not found — skipping permission fix"
fi

# ── Step 4: Doppler service token ────────────────────────────────────────
# Uses a Doppler service token instead of interactive login. The token is
# scoped to chat-force/dev, cached on the host, and injected into the
# container. No interactive Doppler login needed — ever.

step "Doppler setup"

# Resolve the container ID (may already be set from step 3b)
if [ -z "$CONTAINER_ID" ]; then
  CONTAINER_ID=$(docker ps -qf "label=devcontainer.local_folder=$WORKSPACE")
fi

if [ -z "$CONTAINER_ID" ]; then
  error "Could not find running devcontainer. Skipping Doppler setup."
else
  # Check for cached service token first
  if [ -f "$DOPPLER_TOKEN_FILE" ]; then
    DOPPLER_SERVICE_TOKEN=$(cat "$DOPPLER_TOKEN_FILE")
    # Verify the token still works
    if docker exec -e "DOPPLER_TOKEN=$DOPPLER_SERVICE_TOKEN" "$CONTAINER_ID" \
      doppler secrets --only-names &>/dev/null 2>&1; then
      ok "Doppler service token valid (cached)"
    else
      warn "Cached service token expired — will create a new one"
      rm -f "$DOPPLER_TOKEN_FILE"
      DOPPLER_SERVICE_TOKEN=""
    fi
  fi

  # Create a new service token if we don't have one
  if [ -z "${DOPPLER_SERVICE_TOKEN:-}" ]; then
    if ! command -v doppler &>/dev/null; then
      error "Doppler CLI not found on host. Install it: brew install dopplerhq/cli/doppler"
      error "Then run: doppler login && doppler setup --project chat-force --config dev"
      exit 1
    fi

    if ! doppler me &>/dev/null; then
      error "Doppler not authenticated on host."
      error "Run: doppler login"
      exit 1
    fi

    # Ensure host CLI is linked to the right project
    info "Creating Doppler service token for container..."
    DOPPLER_SERVICE_TOKEN=$(doppler configs tokens create \
      --project chat-force --config dev \
      --name "openclaw-container" --plain 2>/dev/null || true)

    if [ -z "$DOPPLER_SERVICE_TOKEN" ]; then
      # Token with that name may already exist — try to reuse
      warn "Could not create token (may already exist). Trying with unique name..."
      DOPPLER_SERVICE_TOKEN=$(doppler configs tokens create \
        --project chat-force --config dev \
        --name "openclaw-container-$(date +%s)" --plain 2>/dev/null || true)
    fi

    if [ -n "$DOPPLER_SERVICE_TOKEN" ]; then
      echo "$DOPPLER_SERVICE_TOKEN" > "$DOPPLER_TOKEN_FILE"
      chmod 600 "$DOPPLER_TOKEN_FILE"
      ok "Doppler service token created and cached"
    else
      error "Failed to create Doppler service token."
      error "Make sure your host Doppler CLI is set up:"
      error "  doppler login"
      error "  doppler setup --project chat-force --config dev"
      exit 1
    fi
  fi

  # Inject the token into the container's environment
  # Write it to a file inside the container that start-openclaw.sh reads
  docker exec "$CONTAINER_ID" bash -c \
    "echo 'DOPPLER_TOKEN=$DOPPLER_SERVICE_TOKEN' > /home/node/.openclaw/.env.doppler && chmod 600 /home/node/.openclaw/.env.doppler"
  ok "Doppler token injected into container"
fi

# ── Step 5: OpenAI Codex OAuth setup ──────────────────────────────────────

step "OpenAI Codex OAuth setup (inside container)"

if [ -z "$CONTAINER_ID" ]; then
  CONTAINER_ID=$(docker ps -qf "label=devcontainer.local_folder=$WORKSPACE")
fi

if [ -n "$CONTAINER_ID" ]; then
  # Check if Codex OAuth is already configured
  if docker exec "$CONTAINER_ID" test -f /home/node/.openclaw/agents/main/agent/auth-profiles.json && \
     docker exec "$CONTAINER_ID" grep -q '"openai-codex"' /home/node/.openclaw/agents/main/agent/auth-profiles.json 2>/dev/null; then
    ok "OpenAI Codex OAuth already configured"
  elif [ -t 0 ]; then
    info "Setting up OpenAI Codex OAuth (uses your ChatGPT subscription)."
    info "You will be prompted to authorize via your browser."
    info ""
    if docker exec -it "$CONTAINER_ID" openclaw onboard --non-interactive --accept-risk --auth-choice openai-codex; then
      ok "OpenAI Codex OAuth configured"
    else
      warn "Codex OAuth setup was not completed. You can finish it later:"
      warn "  docker exec -it $CONTAINER_ID openclaw onboard --auth-choice openai-codex"
    fi
  else
    warn "No TTY available — cannot run interactive Codex OAuth setup."
    warn "Run this in your terminal:"
    warn "  docker exec -it $CONTAINER_ID openclaw onboard --auth-choice openai-codex"
  fi
else
  warn "Container not found. Skipping Codex OAuth setup."
fi

# ── Step 6: Summary ──────────────────────────────────────────────────────

step "Provisioning complete"

echo ""
echo -e "${BOLD}Workspace:${RESET}  $WORKSPACE"
echo -e "${BOLD}Container:${RESET}  OpenClaw Self-Hosted"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo ""
echo "  1. Open a shell in the container:"
echo "     devcontainer exec --workspace-folder $WORKSPACE /bin/bash"
echo ""
echo "  2. Start OpenClaw:"
echo "     /opt/start-openclaw.sh"
echo "     # or: doppler run -- openclaw gateway --bind lan --port 18789"
echo ""
echo "  3. The gateway will be available at:"
echo "     http://localhost:18789"
echo ""
echo "  To stop the container:"
echo "     docker stop \$(docker ps -qf label=devcontainer.local_folder=$WORKSPACE)"
echo ""
echo "  To re-provision (idempotent):"
echo "     $SCRIPT_DIR/provision.sh"
echo ""
echo "  To wipe and re-provision from scratch:"
echo "     $SCRIPT_DIR/provision.sh --clean"
echo ""
echo "  To tear down everything (container + volumes + workspace):"
echo "     $SCRIPT_DIR/provision.sh --destroy"
echo ""
