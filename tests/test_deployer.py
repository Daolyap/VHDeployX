"""Tests for vhdeployx.deployer – deployment orchestration."""

import platform
from unittest.mock import MagicMock, patch

import pytest

from vhdeployx.deployer import Deployer, DeploymentStatus
from vhdeployx.disk import DiskInfo
from vhdeployx.formats import ImageFormat, ImageInfo
from pathlib import Path


@pytest.fixture
def sample_image(tmp_path: Path) -> ImageInfo:
    f = tmp_path / "test.wim"
    f.write_bytes(b"MSWIM\x00\x00\x00" + b"\x00" * 512)
    return ImageInfo(
        path=f,
        format=ImageFormat.WIM,
        size_bytes=f.stat().st_size,
        valid_signature=True,
        description="Windows Imaging Format",
    )


@pytest.fixture
def sample_disk() -> DiskInfo:
    return DiskInfo(
        index=1,
        name="Test Disk",
        size_bytes=100_000_000_000,
        size_display="93.1 GB",
        media_type="SSD",
        partitions=2,
    )


class TestDeployer:
    def test_initial_status(self):
        d = Deployer()
        assert d.status == DeploymentStatus.IDLE
        assert d.is_running is False

    def test_deploy_raises_on_non_windows(self, sample_image, sample_disk):
        """On Linux the deployment should fail with RuntimeError."""
        if platform.system() == "Windows":
            pytest.skip("Test only valid on non-Windows")
        d = Deployer()
        messages: list[str] = []

        def on_progress(pct: int, msg: str):
            messages.append(msg)

        d.deploy(sample_image, sample_disk, progress_cb=on_progress)
        # Wait for thread to complete
        d._thread.join(timeout=5)
        assert d.status == DeploymentStatus.FAILED

    def test_cannot_deploy_twice(self, sample_image, sample_disk):
        d = Deployer()
        d._status = DeploymentStatus.RUNNING
        with pytest.raises(RuntimeError, match="already in progress"):
            d.deploy(sample_image, sample_disk)
