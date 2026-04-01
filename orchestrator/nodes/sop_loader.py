"""SOP discovery, loading, and matching.

SOPs (Standard Operating Procedures) live as YAML files in two locations:
  - Platform-wide:  ``platform/sops/`` (available to all workspaces)
  - Workspace-specific:  ``workspaces/{id}/sops/`` (scoped to one client)

This module provides helpers to list available SOPs, load a specific one,
and match a user's input to the most relevant SOP.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_yaml_safe(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict on any error."""
    try:
        text = path.read_text(encoding="utf-8")
        return yaml.safe_load(text) or {}
    except FileNotFoundError:
        return {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to load SOP at %s: %s", path, exc)
        return {}


def _sop_dirs(workspace_id: str) -> list[Path]:
    """Return the list of directories to search for SOPs, in priority order.

    Workspace-specific SOPs take precedence over platform-wide ones.
    """
    dirs: list[Path] = []
    ws_sops = _PROJECT_ROOT / "workspaces" / workspace_id / "sops"
    if ws_sops.is_dir():
        dirs.append(ws_sops)
    platform_sops = _PROJECT_ROOT / "platform" / "sops"
    if platform_sops.is_dir():
        dirs.append(platform_sops)
    return dirs


def list_sops(workspace_id: str) -> list[dict[str, Any]]:
    """List all SOPs available for a workspace (platform + workspace-specific).

    Parameters
    ----------
    workspace_id:
        Directory name under ``workspaces/``.

    Returns
    -------
    list[dict]
        Each dict has ``name``, ``description``, ``source`` (``"workspace"`` or
        ``"platform"``), and ``path``.
    """
    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for sop_dir in _sop_dirs(workspace_id):
        source = "workspace" if "workspaces" in str(sop_dir) else "platform"
        for yaml_file in sorted(sop_dir.glob("*.yaml")):
            data = _load_yaml_safe(yaml_file)
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


def load_sop(workspace_id: str, sop_name: str) -> dict[str, Any]:
    """Load a specific SOP definition from YAML.

    Searches workspace SOPs first, then platform SOPs.

    Parameters
    ----------
    workspace_id:
        Directory name under ``workspaces/``.
    sop_name:
        The SOP name to look for (matched against the ``name`` field in YAML,
        or the filename stem as a fallback).

    Returns
    -------
    dict
        The full parsed SOP definition.

    Raises
    ------
    FileNotFoundError
        If no matching SOP is found.
    """
    for sop_dir in _sop_dirs(workspace_id):
        for yaml_file in sop_dir.glob("*.yaml"):
            data = _load_yaml_safe(yaml_file)
            file_name = data.get("name", yaml_file.stem)
            # Match by name field or filename stem (case-insensitive)
            if (
                file_name.lower() == sop_name.lower()
                or yaml_file.stem.lower() == sop_name.lower()
            ):
                return data

    raise FileNotFoundError(f"SOP '{sop_name}' not found for workspace '{workspace_id}'")


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
        Directory name under ``workspaces/``.

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
