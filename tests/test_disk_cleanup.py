"""Tests for pipeline/disk_cleanup.py."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from pipeline.disk_cleanup import DiskCleanupThread


class TestDiskCleanup:
    """Test disk cleanup of old run directories."""

    def test_prunes_old_directories(self, tmp_path: Path) -> None:
        """Directories older than retention_days should be pruned."""
        # Create an "old" directory (backdate mtime)
        old_dir = tmp_path / "20260101-000000-old"
        old_dir.mkdir()
        (old_dir / "summary.json").write_text("{}")
        old_mtime = time.time() - (8 * 86400)  # 8 days ago
        os.utime(old_dir, (old_mtime, old_mtime))

        # Create a "new" directory (recent)
        new_dir = tmp_path / "20260406-000000-new"
        new_dir.mkdir()
        (new_dir / "summary.json").write_text("{}")

        cleanup = DiskCleanupThread(str(tmp_path), retention_days=7)
        pruned = cleanup.cleanup_once()

        assert pruned == 1
        assert not old_dir.exists()
        assert new_dir.exists()

    def test_keeps_recent_directories(self, tmp_path: Path) -> None:
        """Directories within the retention window should be kept."""
        recent = tmp_path / "20260405-120000-recent"
        recent.mkdir()
        (recent / "data.txt").write_text("keep me")

        cleanup = DiskCleanupThread(str(tmp_path), retention_days=7)
        pruned = cleanup.cleanup_once()

        assert pruned == 0
        assert recent.exists()

    def test_handles_empty_output_base(self, tmp_path: Path) -> None:
        """Should handle an empty output directory gracefully."""
        cleanup = DiskCleanupThread(str(tmp_path), retention_days=7)
        pruned = cleanup.cleanup_once()
        assert pruned == 0

    def test_handles_nonexistent_output_base(self) -> None:
        """Should handle a nonexistent output directory gracefully."""
        cleanup = DiskCleanupThread("/nonexistent/path", retention_days=7)
        pruned = cleanup.cleanup_once()
        assert pruned == 0

    def test_skips_files(self, tmp_path: Path) -> None:
        """Should only prune directories, not files."""
        old_file = tmp_path / "stale.log"
        old_file.write_text("old log")
        old_mtime = time.time() - (30 * 86400)
        os.utime(old_file, (old_mtime, old_mtime))

        cleanup = DiskCleanupThread(str(tmp_path), retention_days=7)
        pruned = cleanup.cleanup_once()

        assert pruned == 0
        assert old_file.exists()

    def test_thread_starts_and_stops(self, tmp_path: Path) -> None:
        """Background thread should start and stop cleanly."""
        cleanup = DiskCleanupThread(str(tmp_path), retention_days=7, interval=1)
        cleanup.start()
        assert cleanup._thread is not None
        assert cleanup._thread.is_alive()

        cleanup.stop()
        assert cleanup._thread is None

    def test_multiple_old_dirs_pruned(self, tmp_path: Path) -> None:
        """All old directories should be pruned in a single pass."""
        old_mtime = time.time() - (10 * 86400)
        for i in range(5):
            d = tmp_path / f"run-{i}"
            d.mkdir()
            os.utime(d, (old_mtime, old_mtime))

        cleanup = DiskCleanupThread(str(tmp_path), retention_days=7)
        pruned = cleanup.cleanup_once()
        assert pruned == 5
