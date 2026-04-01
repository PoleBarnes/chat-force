#!/usr/bin/env bash
set -e

# Substitute environment variables into config templates and copy them
# to the location OpenClaw expects. The templates are mounted read-only
# at /templates/; the real config dir is writable.

CONFIG_DIR="/home/openclaw/.openclaw"
TEMPLATE_DIR="/templates"

for template in "$TEMPLATE_DIR"/*.json; do
  [ -f "$template" ] || continue
  filename="$(basename "$template")"
  envsubst < "$template" > "$CONFIG_DIR/$filename"
done

# Hand off to the OpenClaw gateway
exec openclaw gateway --bind lan --allow-unconfigured
