"""Hourly background thread that prunes old session run directories.

The engine writes session artifacts (changeset bundles, tool logs, worker
logs, summaries) to ``{output_base}/{run_id}/``. Over time these
accumulate. This module provides a background thread that wakes hourly
and deletes subtrees older than a configurable retention period.

Usage::

    from pipeline.disk_cleanup import DiskCleanupThread

    cleanup = DiskCleanupThread(output_base="/tmp/chat-force-runs", retention_days=7)
    cleanup.start()
    # ... engine runs ...
    cleanup.stop()
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

# How often the cleanup thread wakes up (seconds).
_CLEANUP_INTERVAL = 3600  # 1 hour


class DiskCleanupThread:
    """Background thread that prunes old run directories.

    Each run directory is named ``{timestamp}-{hex}`` (e.g.,
    ``20260406-023121-b49efabe``). The thread checks the directory's
    modification time, not the name, to decide whether to prune.
    """

    def __init__(
        self,
        output_base: str,
        retention_days: int = 7,
        interval: int = _CLEANUP_INTERVAL,
    ):
        self._output_base = Path(output_base)
        self._retention_seconds = retention_days * 86400
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the cleanup background thread."""
        if self._thread is not None and self._thread.is_alive():
            log.warning("Disk cleanup thread already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="disk-cleanup",
        )
        self._thread.start()
        log.info(
            "Disk cleanup started (base=%s, retention=%dd, interval=%ds)",
            self._output_base,
            self._retention_seconds // 86400,
            self._interval,
        )

    def stop(self) -> None:
        """Stop the cleanup thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        log.info("Disk cleanup stopped")

    def cleanup_once(self) -> int:
        """Run a single cleanup pass. Returns the number of directories pruned.

        Public so tests can call it directly without starting the thread.
        """
        if not self._output_base.is_dir():
            return 0

        now = time.time()
        cutoff = now - self._retention_seconds
        pruned = 0

        for entry in self._output_base.iterdir():
            if not entry.is_dir():
                continue
            try:
                mtime = entry.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(entry)
                    log.info("Pruned old run directory: %s", entry.name)
                    pruned += 1
            except OSError:
                log.debug("Could not stat/prune %s", entry, exc_info=True)

        if pruned:
            log.info("Disk cleanup: pruned %d directories", pruned)
        return pruned

    def _run_loop(self) -> None:
        """Background loop: clean once per interval."""
        log.debug("Disk cleanup thread started")
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            try:
                self.cleanup_once()
            except Exception:
                log.warning("Disk cleanup error", exc_info=True)
        log.debug("Disk cleanup thread exiting")
