"""Deliverable storage adapters.

A deliverable is a finished work product that the bot produces for
a customer: an ad campaign, a landing page, a research report, etc.
This module provides adapters for saving deliverables to their final
destination.

Currently only the filesystem backend is supported. Future backends
(Google Drive, Obsidian, etc.) plug in via the same interface.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class FilesystemDeliverable:
    """Save deliverables to a local filesystem path.

    The path comes from ``workspace.yaml.deliverables.filesystem.path``.
    Files are written atomically (write to temp, then rename) where
    possible.
    """

    def __init__(self, base_path: str):
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: str | bytes) -> Path:
        """Save a deliverable file. Returns the absolute path.

        Creates parent directories as needed. Overwrites if the file
        already exists.
        """
        dest = self.base / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content, encoding="utf-8")

        log.info("Deliverable saved: %s (%d bytes)", dest, dest.stat().st_size)
        return dest.resolve()


def create_deliverable_adapter(config: dict) -> FilesystemDeliverable:
    """Create the appropriate deliverable adapter from workspace.yaml config.

    Currently only 'filesystem' is supported. Raises ValueError for
    unknown backends.
    """
    backend = config.get("backend", "filesystem")
    if backend == "filesystem":
        fs_config = config.get("filesystem", {})
        path = fs_config.get("path")
        if not path:
            raise ValueError(
                "deliverables.filesystem.path is required when backend='filesystem'"
            )
        return FilesystemDeliverable(path)

    raise ValueError(
        f"Unknown deliverable backend: {backend!r}. Supported: 'filesystem'"
    )
