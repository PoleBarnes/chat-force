"""Node implementations for the Digital Workforce Platform orchestrator.

This package contains the building blocks used by the LangGraph graphs:
  - agents: Agent dispatch interface for multi-agent SOP execution
  - context: Three-tier context assembly (platform -> workspace -> thread)
  - llm: Thin wrapper around the Anthropic SDK
  - routing: Task routing decision logic
  - sop_loader: SOP discovery, loading, and matching
  - specialists: Canonical specialist system prompts
  - utils: Shared helpers (YAML loading, file reading, PROJECT_ROOT)
"""

from .agents import dispatch
from .context import assemble_context
from .llm import call_claude, call_claude_structured, get_client, get_temperature
from .routing import should_dispatch
from .sop_loader import SOPDefinition, SOPStep, list_sops, load_sop, load_sop_from_path, match_sop
from .specialists import SPECIALIST_PROMPTS, get_specialist_prompt
from .utils import PROJECT_ROOT, load_yaml_safe, read_file_safe

__all__ = [
    "PROJECT_ROOT",
    "SOPDefinition",
    "SOPStep",
    "SPECIALIST_PROMPTS",
    "assemble_context",
    "call_claude",
    "call_claude_structured",
    "dispatch",
    "get_client",
    "get_specialist_prompt",
    "get_temperature",
    "list_sops",
    "load_sop",
    "load_sop_from_path",
    "load_yaml_safe",
    "match_sop",
    "read_file_safe",
    "should_dispatch",
]
