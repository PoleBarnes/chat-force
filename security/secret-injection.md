# Secret Injection Flow

## Architecture

```
Doppler (vault)
    |
    v  (env vars injected at container boot)
Container Environment
    |
    v  (os.environ lookup at call time)
Tool / API Call
    |
    v  (scrubbed from response before return)
Agent Context (never sees raw secret values)
```

The agent never handles raw secrets directly. Secrets flow from Doppler
through environment variables into SDK calls, and the agent only references
them by name.

## Doppler Organization

Secrets are organized per-workspace with environment-based configs:

```
Project: chat-force
  |
  +-- dev         (local development)
  +-- staging     (pre-production testing)
  +-- production  (live environment)
```

Each environment contains the same set of secret names with
environment-appropriate values:

| Secret Name              | Purpose                          |
|--------------------------|----------------------------------|
| `ANTHROPIC_API_KEY`      | Claude API access                |
| `SLACK_BOT_TOKEN`        | Slack bot interactions           |
| `SLACK_APP_TOKEN`        | Slack socket mode                |
| `SLACK_SIGNING_SECRET`   | Webhook verification             |
| `GITHUB_TOKEN`           | Repository access                |
| `ANTHROPIC_API_KEY`      | Claude API access                |

## Environment Variable Convention

All secret env vars follow these rules:

- **UPPER_SNAKE_CASE** names
- **Prefixed by service**: `SLACK_`, `GITHUB_`, `ANTHROPIC_`, etc.
- **No secrets in files**: Never written to `.env` files in production
  (Doppler injects directly into the container environment)
- **Local dev**: Use `doppler run -- <command>` to inject secrets for
  local execution without writing `.env` files

## How the Anthropic SDK Picks Up the Key

The Anthropic Python SDK automatically reads `ANTHROPIC_API_KEY` from
the environment:

```python
import anthropic

# No key parameter needed — SDK reads os.environ["ANTHROPIC_API_KEY"]
client = anthropic.Anthropic()
```

Doppler ensures this variable is present in every environment where the
agent runs. The agent code never contains the key value.

## How LangGraph Tools Resolve Secrets

When a LangGraph tool needs a secret (e.g., a Slack token to post a message),
it resolves the secret at call time from the environment:

```python
import os

def post_slack_message(channel: str, text: str) -> dict:
    token = os.environ["SLACK_BOT_TOKEN"]  # resolved at runtime
    # ... use token in API call ...
    # token is never returned to the agent or logged
```

The tool function:
1. Reads the env var at the moment of execution
2. Uses it in the API call
3. Returns only the API response (status, message ID, etc.)
4. Never includes the token value in the return

## Audit Logging of Secret Access

The audit logger tracks that a secret was accessed without logging the
secret value itself:

```python
logger.log_secret_access(
    secret_name="SLACK_BOT_TOKEN",
    purpose="post message to #general",
)
```

This produces an audit event like:

```json
{
  "timestamp": "2026-04-01T12:00:00+00:00",
  "event_type": "secret_access",
  "workspace_id": "ws-leo-001",
  "details": {
    "secret_name": "SLACK_BOT_TOKEN",
    "purpose": "post message to #general",
    "note": "Secret value not logged — only access event recorded."
  },
  "scrubbed": false
}
```

If a secret value accidentally appears in a log entry (e.g., in an error
message), the audit logger's `sensitive=True` mode scrubs it:

```python
# If an error response accidentally includes a token
logger.log(AuditEventType.TASK_ERROR, {
    "error": "Auth failed with token xoxb-123-456-abc",
}, sensitive=True)

# Logged as:
# { "details": { "error": "[REDACTED]" }, "scrubbed": true }
```

## Security Properties

1. **Secrets never in code**: All secrets live in Doppler, injected via env vars
2. **Secrets never in logs**: Audit logger scrubs known secret patterns
3. **Secrets never in git**: Pre-push hook scans for secret patterns
4. **Secrets never in agent context**: Tools consume secrets internally
   and return only results
5. **Access is audited**: Every secret access is logged by name and purpose
6. **Rotation is seamless**: Update in Doppler, restart container, done
