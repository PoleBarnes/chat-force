"""Tests for pipeline/deliverables.py — deliverable storage adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.deliverables import FilesystemDeliverable, create_deliverable_adapter


class TestFilesystemDeliverable:
    """Test filesystem-based deliverable storage."""

    def test_save_text_file(self, tmp_path: Path) -> None:
        adapter = FilesystemDeliverable(str(tmp_path / "deliverables"))
        result = adapter.save("report.md", "# Campaign Report\n\nContent here.")
        assert result.exists()
        assert result.read_text() == "# Campaign Report\n\nContent here."

    def test_save_binary_file(self, tmp_path: Path) -> None:
        adapter = FilesystemDeliverable(str(tmp_path / "deliverables"))
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = adapter.save("logo.png", data)
        assert result.exists()
        assert result.read_bytes() == data

    def test_creates_subdirectories(self, tmp_path: Path) -> None:
        adapter = FilesystemDeliverable(str(tmp_path / "deliverables"))
        result = adapter.save("campaigns/spring-2026/brief.md", "Brief content")
        assert result.exists()
        assert "campaigns/spring-2026" in str(result)

    def test_creates_base_directory(self, tmp_path: Path) -> None:
        base = tmp_path / "new" / "deep" / "path"
        adapter = FilesystemDeliverable(str(base))
        assert base.is_dir()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        adapter = FilesystemDeliverable(str(tmp_path))
        adapter.save("file.txt", "v1")
        adapter.save("file.txt", "v2")
        assert (tmp_path / "file.txt").read_text() == "v2"

    def test_returns_absolute_path(self, tmp_path: Path) -> None:
        adapter = FilesystemDeliverable(str(tmp_path))
        result = adapter.save("output.txt", "data")
        assert result.is_absolute()


class TestCreateDeliverableAdapter:
    """Test the adapter factory."""

    def test_filesystem_backend(self, tmp_path: Path) -> None:
        config = {"backend": "filesystem", "filesystem": {"path": str(tmp_path)}}
        adapter = create_deliverable_adapter(config)
        assert isinstance(adapter, FilesystemDeliverable)

    def test_missing_path_raises(self) -> None:
        config = {"backend": "filesystem", "filesystem": {}}
        with pytest.raises(ValueError, match="path is required"):
            create_deliverable_adapter(config)

    def test_unknown_backend_raises(self) -> None:
        config = {"backend": "google_drive"}
        with pytest.raises(ValueError, match="Unknown deliverable backend"):
            create_deliverable_adapter(config)

    def test_default_backend_is_filesystem(self, tmp_path: Path) -> None:
        config = {"filesystem": {"path": str(tmp_path)}}
        adapter = create_deliverable_adapter(config)
        assert isinstance(adapter, FilesystemDeliverable)
