"""SOP discovery, loading, and matching.

SOPs (Standard Operating Procedures) live as YAML files in:
  - ``sops/`` (platform-level SOP templates, available to all workspaces)

This module provides helpers to list available SOPs, load a specific one,
and match a user's input to the most relevant SOP.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from .utils import PROJECT_ROOT, load_yaml_safe

logger = logging.getLogger(__name__)


def _validate_workspace_id(workspace_id: str) -> str:
    """Validate workspace_id to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', workspace_id):
        raise ValueError(
            f"Invalid workspace_id: {workspace_id!r} "
            "— must be alphanumeric with hyphens/underscores only"
        )
    return workspace_id


# ---------------------------------------------------------------------------
# SOP data model (canonical location -- imported by sop_runner and main graph)
# ---------------------------------------------------------------------------

class SOPStep(BaseModel):
    """A single step inside an SOP definition."""
    id: str
    description: str = ""
    specialist: str = ""
    agent: str = ""  # Agent dispatcher (e.g. "openclaw", "perplexity", "api:gemini")
    type: str = "task"  # "task" or "approval_gate"
    depends_on: list[str] = Field(default_factory=list)


class SOPDefinition(BaseModel):
    """Parsed representation of an SOP YAML file."""
    name: str
    version: int = 1
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[SOPStep] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)


def _sop_dirs(workspace_id: str) -> list[Path]:
    """Return the list of directories to search for SOPs.

    All SOPs live at the platform level in ``sops/``.
    """
    _validate_workspace_id(workspace_id)
    dirs: list[Path] = []
    sops_dir = PROJECT_ROOT / "sops"
    if sops_dir.is_dir():
        dirs.append(sops_dir)
    return dirs


def list_sops(workspace_id: str) -> list[dict[str, Any]]:
    """List all SOPs available for a workspace.

    Parameters
    ----------
    workspace_id:
        Workspace identifier (currently unused; all SOPs are platform-level).

    Returns
    -------
    list[dict]
        Each dict has ``name``, ``description``, ``source`` (``"workspace"`` or
        ``"platform"``), and ``path``.
    """
    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for sop_dir in _sop_dirs(workspace_id):
        source = "platform"
        for yaml_file in sorted(sop_dir.glob("*.yaml")):
            data = load_yaml_safe(yaml_file)
            name = data.get("name", yaml_file.stem)
            if name in seen_names:
                continue  # Workspace-level SOP already found with this name
            seen_names.add(name)
            results.append({
                "name": name,
                "description": data.get("description", ""),
                "source": source,
                "path": str(yaml_file),
            })

    return results


def load_sop(workspace_id: str, sop_name: str) -> SOPDefinition:
    """Load a specific SOP definition from YAML.

    Searches the platform-level ``sops/`` directory and returns a validated
    ``SOPDefinition`` Pydantic model.

    Parameters
    ----------
    workspace_id:
        Workspace identifier (currently unused; all SOPs are platform-level).
    sop_name:
        The SOP name to look for (matched against the ``name`` field in YAML,
        or the filename stem as a fallback).

    Returns
    -------
    SOPDefinition
        Parsed and validated SOP definition.

    Raises
    ------
    FileNotFoundError
        If no matching SOP is found.
    """
    for sop_dir in _sop_dirs(workspace_id):
        for yaml_file in sop_dir.glob("*.yaml"):
            data = load_yaml_safe(yaml_file)
            file_name = data.get("name", yaml_file.stem)
            # Match by name field or filename stem (case-insensitive)
            if (
                file_name.lower() == sop_name.lower()
                or yaml_file.stem.lower() == sop_name.lower()
            ):
                return _parse_sop_definition(data)

    raise FileNotFoundError(f"SOP '{sop_name}' not found for workspace '{workspace_id}'")


def _parse_sop_definition(raw: dict[str, Any]) -> SOPDefinition:
    """Parse a raw YAML dict into a validated SOPDefinition model."""
    steps = raw.get("steps", [])
    normalized_steps = []
    for step_raw in steps:
        step_type = step_raw.get("type", "task")
        # Normalize "human_approval" to "approval_gate" for consistency
        if step_type == "human_approval":
            step_type = "approval_gate"
        normalized_steps.append(SOPStep(
            id=step_raw.get("id", ""),
            description=step_raw.get("description", ""),
            specialist=step_raw.get("specialist", step_raw.get("agent", "general")),
            agent=step_raw.get("agent", step_raw.get("specialist", "openclaw")),
            type=step_type,
            depends_on=step_raw.get("depends_on", []),
        ))

    return SOPDefinition(
        name=raw.get("name", "unknown"),
        version=raw.get("version", 1),
        description=raw.get("description", ""),
        input_schema=raw.get("input_schema", raw.get("inputs", {})),
        steps=normalized_steps,
        output_schema=raw.get("output_schema", {}),
    )


def load_sop_from_path(path: Path | str) -> SOPDefinition:
    """Load and validate an SOP from a YAML file path.

    Parameters
    ----------
    path:
        Path to the SOP YAML file.

    Returns
    -------
    SOPDefinition
        Parsed and validated SOP definition.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    ValueError
        If the YAML is malformed or missing required fields.
    """
    sop_path = Path(path)
    if not sop_path.exists():
        raise FileNotFoundError(f"SOP file not found: {sop_path}")

    try:
        raw = yaml.safe_load(sop_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {sop_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"SOP file must contain a YAML mapping, got {type(raw).__name__}")

    if "name" not in raw:
        raise ValueError(f"SOP file {sop_path} is missing required field 'name'")

    return _parse_sop_definition(raw)


def match_sop(user_input: str, workspace_id: str) -> Optional[str]:
    """Try to match user input to a registered SOP.

    Matching strategy:
      1. Exact name match (case-insensitive) against known SOP names
      2. Keyword overlap — check if the user input contains significant words
         from the SOP name or description

    Parameters
    ----------
    user_input:
        The raw text from the user.
    workspace_id:
        Workspace identifier (currently unused; all SOPs are platform-level).

    Returns
    -------
    str or None
        The matched SOP name, or ``None`` if no match is found.
    """
    available = list_sops(workspace_id)
    if not available:
        return None

    input_lower = user_input.lower()

    # Pass 1: Exact name match
    for sop in available:
        sop_name_lower = sop["name"].lower()
        if sop_name_lower in input_lower:
            logger.info("SOP matched (exact): %s", sop["name"])
            return sop["name"]

    # Pass 2: Keyword overlap scoring
    # Strip punctuation and tokenize into meaningful words (2+ chars)
    import re
    _punct = re.compile(r"[^\w\s]")

    input_clean = _punct.sub("", input_lower)
    input_words = {w for w in input_clean.split() if len(w) >= 2}

    stop_words = {
        "the", "and", "for", "from", "with", "that", "this", "are", "was",
        "has", "have", "been", "will", "can", "should", "would", "our",
        "an", "is", "it", "its", "of", "to", "in", "on", "by", "be",
        "do", "if", "so", "or", "no", "not", "all", "any", "each",
    }
    input_words_clean = input_words - stop_words

    best_match: Optional[str] = None
    best_score = 0.0

    for sop in available:
        # Build keyword set from name + description
        sop_text = f"{sop['name']} {sop.get('description', '')}".lower()
        sop_clean_text = _punct.sub("", sop_text)
        sop_words = {w for w in sop_clean_text.split() if len(w) >= 2}
        sop_words -= stop_words

        if not sop_words:
            continue

        # Check for high-value name keywords specifically
        name_words = {
            w for w in _punct.sub("", sop["name"].lower()).split()
            if len(w) >= 2
        } - stop_words
        name_overlap = len(input_words_clean & name_words)

        # General keyword overlap
        overlap = len(input_words_clean & sop_words)

        # Score: weight name-word matches more heavily
        score = (name_overlap * 2.0 + overlap) / (len(name_words) * 2.0 + len(sop_words))

        if score > best_score and overlap >= 1:
            best_score = score
            best_match = sop["name"]

    if best_match and best_score >= 0.08:
        logger.info("SOP matched (keyword, score=%.2f): %s", best_score, best_match)
        return best_match

    return None
