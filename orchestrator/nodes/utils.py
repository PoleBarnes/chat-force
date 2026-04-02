"""Shared utility functions for orchestrator nodes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Project root: three levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def read_file_safe(path: Path) -> str:
    """Read a file and return its contents, or empty string on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.debug("File not found: %s", path)
        return ""
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return ""


def load_yaml_safe(path: Path) -> dict[str, Any]:
    """Load a YAML file and return a dict, or empty dict on failure."""
    text = read_file_safe(path)
    if not text:
        return {}
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in %s: %s", path, exc)
        return {}
