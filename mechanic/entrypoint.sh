#!/bin/bash
set -euo pipefail

# Validate required env vars
: "${TASK_DESCRIPTION:?TASK_DESCRIPTION env var is required}"
: "${ANTHROPIC_AUTH_TOKEN:?ANTHROPIC_AUTH_TOKEN env var is required}"

# OpenClaw --local mode reads ANTHROPIC_API_KEY from the environment
export ANTHROPIC_API_KEY="${ANTHROPIC_AUTH_TOKEN}"

echo "[Mechanic] Evaluating changeset for task: ${TASK_DESCRIPTION}"

# Build the evaluation prompt from the changeset bundle
CHANGESET_FILE="/changeset/changeset.json"
if [ ! -f "$CHANGESET_FILE" ]; then
  echo "[Mechanic] ERROR: No changeset file found at $CHANGESET_FILE"
  echo '{"verdict":"reject","approved":false,"confidence":0.0,"summary":"No changeset file found","rejection_reason":"Changeset file missing at /changeset/changeset.json"}' > /output/verdict.json
  exit 0
fi

# Construct the evaluation message
MESSAGE="Evaluate this changeset. The original task was:

${TASK_DESCRIPTION}

Here is the full changeset bundle (JSON):

$(cat "$CHANGESET_FILE")

After your evaluation, write your verdict as JSON to /output/verdict.json following the schema in your AGENTS.md instructions."

# Run OpenClaw in local mode
openclaw agent \
  --local \
  --agent main \
  --message "$MESSAGE" \
  --json \
  > /tmp/mechanic-output.json 2>&1 || true

echo "[Mechanic] Evaluation complete"

# Check if verdict was written
if [ ! -f /output/verdict.json ]; then
  echo "[Mechanic] WARNING: Agent did not write verdict.json — creating rejection"
  echo '{"verdict":"reject","approved":false,"confidence":0.0,"summary":"Mechanic agent did not produce a verdict file","rejection_reason":"Agent failed to write /output/verdict.json"}' > /output/verdict.json
fi
