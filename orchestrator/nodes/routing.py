"""Task routing decision logic.

Determines whether a user request should be:
  - Handled directly by OpenClaw (simple questions, research, brainstorming)
  - Dispatched to a LangGraph workflow (multi-step tasks, SOP-matching)

The decision is based on:
  1. Keyword matching against ``dispatch_keywords`` in base-config.yaml
  2. SOP matching against registered SOPs for the workspace
  3. Complexity heuristics (multi-step indicators in the input)
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from . import context as ctx
from . import sop_loader

logger = logging.getLogger(__name__)

# Words that indicate multi-step or complex tasks even without a keyword match
_COMPLEXITY_INDICATORS = [
    "step by step",
    "step-by-step",
    "multiple steps",
    "first, then",
    "plan for",
    "workflow",
    "end to end",
    "end-to-end",
    "process for",
    "automate",
    "project plan",
]


def _load_dispatch_keywords() -> list[str]:
    """Load dispatch keywords from platform config."""
    config = ctx.load_platform_config()
    routing = config.get("routing", {})
    keywords = routing.get("dispatch_keywords", [])
    return [k.lower() for k in keywords]


def should_dispatch(
    user_input: str, workspace_id: str
) -> Tuple[bool, Optional[str]]:
    """Decide whether to dispatch to LangGraph and which SOP to use.

    Parameters
    ----------
    user_input:
        The raw text of the user's request.
    workspace_id:
        The workspace directory name.

    Returns
    -------
    Tuple[bool, Optional[str]]
        ``(should_dispatch, matched_sop_name_or_none)``.
        If ``should_dispatch`` is ``True``, the request should be handled by a
        LangGraph workflow. ``matched_sop_name`` is set if a specific SOP was
        identified.
    """
    input_lower = user_input.lower()

    # Check 1: Does the input match a registered SOP?
    matched_sop = sop_loader.match_sop(user_input, workspace_id)
    if matched_sop:
        logger.info("Routing decision: DISPATCH (SOP match: %s)", matched_sop)
        return True, matched_sop

    # Check 2: Does the input contain dispatch keywords from config?
    dispatch_keywords = _load_dispatch_keywords()
    for keyword in dispatch_keywords:
        if keyword in input_lower:
            logger.info(
                "Routing decision: DISPATCH (keyword match: %r)", keyword
            )
            return True, None

    # Check 3: Does the input show complexity indicators?
    for indicator in _COMPLEXITY_INDICATORS:
        if indicator in input_lower:
            logger.info(
                "Routing decision: DISPATCH (complexity indicator: %r)", indicator
            )
            return True, None

    # Default: handle directly (no dispatch)
    logger.info("Routing decision: HANDLE DIRECTLY")
    return False, None
