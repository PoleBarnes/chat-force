"""Pipeline configuration -- all tunables live here.

Customer-specific configuration (bot name, tokens, limits, identity content,
eval criteria, git identity) does NOT live here. It lives in a
`LoadedHarness` snapshot that is loaded at startup by `HarnessLoader` and
attached to this config via the `harness` field. Engine-global tunables
(Docker runtime, retry tuning, engine self-improvement PR routing) stay
here.
"""

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.harness_loader import LoadedHarness


@dataclass
class PipelineConfig:
    # Docker
    worker_image: str = "chat-force-worker:latest"
    docker_network: str = "chat-force-net"

    # Timeouts (seconds)
    worker_timeout: int = 600      # 10 minutes
    mechanic_timeout: int = 300    # 5 minutes

    # Paths
    output_base: str = "/tmp/chat-force-runs"
    config_repo_url: str = "https://github.com/PoleBarnes/chat-force.git"

    # GitHub
    github_repo: str = "PoleBarnes/chat-force"
    pr_branch_prefix: str = "agent-sdk/auto"

    # Session
    session_idle_timeout: int = 600  # 10 minutes

    # Secrets (from Doppler -- never hardcode values here)
    github_token_env: str = "GITHUB_TOKEN"
    claude_code_token_env: str = "ANTHROPIC_API_KEY"
    slack_token_env: str = "SLACK_BOT_TOKEN"
    max_budget_usd: float = 5.0
    max_turns: int = 50
    permission_mode: str = "bypassPermissions"
    allowed_tools: list[str] = field(
        default_factory=lambda: [
            "Bash",
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "WebSearch",
            "WebFetch",
            "Agent",
            "NotebookEdit",
            "TodoWrite",
        ]
    )

    # Customer-scoped config loaded at startup by HarnessLoader. Optional at
    # construction time so unit tests that exercise engine-global defaults
    # can instantiate PipelineConfig() without a harness; production entry
    # points must set this before creating any manager that touches
    # customer-specific state.
    harness: "LoadedHarness | None" = None

    def __post_init__(self):
        os.makedirs(self.output_base, exist_ok=True)
