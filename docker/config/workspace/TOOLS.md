# TOOLS.md — Leo's Environment

## GitHub

- Org: PoleBarnes
- Main repo: PoleBarnes/chat-force (this project — Digital Workforce Platform)
- Use conventional commit messages
- PRs need clear descriptions with what changed and why

## Slack

- Primary communication channel with Travis
- Bot name: Leo
- Socket mode (outbound connection, no webhook URL needed)

## Secrets

- All secrets managed via Doppler (project: chat-force, config: dev)
- Never hardcode secrets. Never commit them to git.
- Available secrets: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_AUTH_TOKEN, GEMINI_API_KEY
