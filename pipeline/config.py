"""Pipeline configuration -- all tunables live here."""

import os
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    # Docker
    worker_image: str = "chat-force-worker:latest"
    mechanic_image: str = "chat-force-mechanic:latest"
    docker_network: str = "chat-force-net"

    # Timeouts (seconds)
    worker_timeout: int = 600      # 10 minutes
    mechanic_timeout: int = 300    # 5 minutes

    # Paths
    output_base: str = "/tmp/chat-force-runs"
    config_repo_url: str = "https://github.com/PoleBarnes/chat-force.git"

    # GitHub
    github_repo: str = "PoleBarnes/chat-force"
    pr_branch_prefix: str = "openclaw/auto"

    # Webhook
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8787

    # Secrets (from Doppler -- never hardcode values here)
    github_token_env: str = "GITHUB_TOKEN"
    anthropic_token_env: str = "ANTHROPIC_AUTH_TOKEN"
    slack_token_env: str = "SLACK_BOT_TOKEN"

    def __post_init__(self):
        os.makedirs(self.output_base, exist_ok=True)
