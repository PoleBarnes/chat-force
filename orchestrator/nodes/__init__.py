"""Node implementations for the Digital Workforce Platform orchestrator.

This package contains the building blocks used by the LangGraph graphs:
  - context: Three-tier context assembly (platform -> workspace -> thread)
  - llm: Thin wrapper around the Anthropic SDK
  - routing: Task routing decision logic
  - sop_loader: SOP discovery, loading, and matching
"""

from .context import assemble_context
from .llm import call_claude, call_claude_structured, get_client
from .routing import should_dispatch
from .sop_loader import list_sops, load_sop, match_sop

__all__ = [
    "assemble_context",
    "call_claude",
    "call_claude_structured",
    "get_client",
    "list_sops",
    "load_sop",
    "match_sop",
    "should_dispatch",
]
