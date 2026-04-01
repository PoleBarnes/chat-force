# OpenClaw Self-Hosted Docker Setup

Self-hosted OpenClaw gateway running in Docker with read-only configuration
mounts to prevent agent self-modification at runtime.

## Prerequisites

- Docker Engine + Docker Compose v2
- An Anthropic API key or OAuth token (from `claude setup-token`)
- Slack bot and app tokens (if using Slack integration)

## Quick Start

### 1. Edit configuration files

Open `config/openclaw.json` and replace the placeholder tokens:

- `REPLACE_ME_SLACK_BOT_TOKEN` — your Slack bot token (`xoxb-...`)
- `REPLACE_ME_SLACK_APP_TOKEN` — your Slack app-level token (`xapp-...`)

Open `config/auth-profiles.json` and replace:

- `REPLACE_WITH_OAUTH_TOKEN` — your Anthropic API key (`sk-ant-...`)

### 2. Set environment variables

Create a `.env` file in this directory (or export the variables):

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENCLAW_GATEWAY_TOKEN=your-gateway-auth-token
TZ=America/New_York
```

To generate an OAuth token from a Claude subscription instead of an API key:

```bash
claude setup-token
```

Paste the resulting token into `config/auth-profiles.json`.

### 3. Start the gateway

```bash
docker compose up -d
```

### 4. Verify it is running

```bash
docker compose logs -f
```

Check the health endpoint:

```bash
curl http://localhost:3001/healthz
```

## Stopping

```bash
docker compose down
```

To also remove persistent data volumes:

```bash
docker compose down -v
```

## Security Notes

- Configuration files are mounted **read-only** (`:ro`) so the agent cannot
  modify its own config, auth profiles, or tokens at runtime.
- The container runs as a non-root user (`openclaw`, uid 1001).
- `NET_RAW` and `NET_ADMIN` capabilities are dropped.
- `no-new-privileges` is enforced.

## File Overview

```
platform/docker/
  Dockerfile              — Image definition (node:22-slim + OpenClaw)
  docker-compose.yml      — Service orchestration
  config/
    openclaw.json          — Gateway and agent configuration
    auth-profiles.json     — Model provider credentials
```
