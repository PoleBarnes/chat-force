# Cron Configuration

This directory contains the cron and proactive behavior configurations for Leo.

## Files

- **heartbeat.yaml** — Heartbeat configuration (every 2 hours during business hours)
- **morning-briefing.yaml** — Morning briefing structure and triggers
- **standing-orders.yaml** — Always-on background behaviors

## How It Works

OpenClaw runs cron jobs natively. These YAML files define:
1. **What** to check on each trigger
2. **When** to trigger (cron schedule or event-based)
3. **How** to notify (actionable, not passive)

The corresponding workspace file (CRON.md) contains the natural language
instructions that Leo follows. The YAML files are the machine-readable config;
CRON.md is what Leo actually reads.

## Adding New Cron Jobs

1. Define the schedule and behavior in a YAML file
2. Add corresponding instructions to CRON.md
3. Test via gateway CLI: `openclaw agent --agent main --message "Run heartbeat check"`
4. Deploy: copy CRON.md to the workspace directory
