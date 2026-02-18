"""Tests for vhdeployx.deployer – deployment orchestration."""

import platform
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from vhdeployx.deployer import (
    Deployer,
    DeploymentStatus,
    _deploy_image,
    _deploy_wim,
    _deploy_vhd,
    _deploy_iso,
    _deploy_img,
    _escape_ps_path,
    _prepare_disk,
    _run_robocopy_ps,
)
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
        with d._lock:
            d._status = DeploymentStatus.RUNNING
        with pytest.raises(RuntimeError, match="already in progress"):
            d.deploy(sample_image, sample_disk)


class TestEscapePsPath:
    def test_no_quotes(self):
        assert _escape_ps_path("C:\\images\\test.vhd") == "C:\\images\\test.vhd"

    def test_single_quotes_escaped(self):
        assert _escape_ps_path("C:\\it's a test.vhd") == "C:\\it''s a test.vhd"

    def test_multiple_quotes(self):
        assert _escape_ps_path("a'b'c") == "a''b''c"


class TestRunRobocopyPs:
    @patch("vhdeployx.deployer.subprocess.run")
    def test_success_exit_0(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _run_robocopy_ps("robocopy src dst")  # should not raise

    @patch("vhdeployx.deployer.subprocess.run")
    def test_success_exit_1_to_7(self, mock_run):
        for code in (1, 2, 3, 4, 5, 6, 7):
            mock_run.return_value = MagicMock(returncode=code)
            _run_robocopy_ps("robocopy src dst")  # should not raise

    @patch("vhdeployx.deployer.subprocess.run")
    def test_failure_exit_8_plus(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=8, args=["powershell"], stdout="out", stderr="err"
        )
        with pytest.raises(subprocess.CalledProcessError):
            _run_robocopy_ps("robocopy src dst")


class TestDeployWim:
    @patch("vhdeployx.deployer.subprocess.run")
    def test_calls_dism_and_bcdboot(self, mock_run, sample_image):
        mock_run.return_value = MagicMock(returncode=0)
        progress = MagicMock()
        _deploy_wim(sample_image, 1, progress)
        assert mock_run.call_count == 2
        # First call should be dism
        dism_call = mock_run.call_args_list[0]
        assert "dism" in dism_call[0][0][0]
        # Second call should be bcdboot
        bcdboot_call = mock_run.call_args_list[1]
        assert "bcdboot" in bcdboot_call[0][0][0]


class TestDeployVhd:
    @patch("vhdeployx.deployer._run_robocopy_ps")
    @patch("vhdeployx.deployer.subprocess.run")
    def test_calls_powershell_and_bcdboot(self, mock_run, mock_robocopy, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        img = ImageInfo(
            path=tmp_path / "test.vhdx",
            format=ImageFormat.VHDX,
            size_bytes=1024,
            valid_signature=True,
        )
        progress = MagicMock()
        _deploy_vhd(img, 1, progress)
        # robocopy helper is called once, then bcdboot via subprocess.run
        mock_robocopy.assert_called_once()
        mock_run.assert_called_once()
        assert "bcdboot" in mock_run.call_args[0][0][0]


class TestDeployIso:
    @patch("vhdeployx.deployer._run_robocopy_ps")
    @patch("vhdeployx.deployer.subprocess.run")
    def test_calls_powershell_and_bcdboot(self, mock_run, mock_robocopy, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        img = ImageInfo(
            path=tmp_path / "test.iso",
            format=ImageFormat.ISO,
            size_bytes=4096,
            valid_signature=True,
        )
        progress = MagicMock()
        _deploy_iso(img, 1, progress)
        mock_robocopy.assert_called_once()
        mock_run.assert_called_once()

    @patch("vhdeployx.deployer._run_robocopy_ps")
    @patch("vhdeployx.deployer.subprocess.run")
    def test_bcdboot_failure_logged_not_raised(self, mock_run, mock_robocopy, tmp_path):
        """bcdboot failure should log a warning but not raise."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "bcdboot")
        img = ImageInfo(
            path=tmp_path / "test.iso",
            format=ImageFormat.ISO,
            size_bytes=4096,
            valid_signature=True,
        )
        progress = MagicMock()
        _deploy_iso(img, 1, progress)  # should not raise


class TestDeployImg:
    @patch("vhdeployx.deployer.subprocess.run")
    def test_calls_powershell(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        img = ImageInfo(
            path=tmp_path / "test.img",
            format=ImageFormat.IMG,
            size_bytes=512,
            valid_signature=True,
        )
        progress = MagicMock()
        _deploy_img(img, 2, progress)
        mock_run.assert_called_once()
        ps_cmd = mock_run.call_args[0][0]
        assert ps_cmd[0] == "powershell"


class TestPrepare:
    @patch("vhdeployx.deployer.subprocess.run")
    def test_prepare_wim(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        _prepare_disk(1, ImageFormat.WIM)
        mock_run.assert_called_once()
        script = mock_run.call_args[1]["input"]
        assert "select disk 1" in script
        assert "convert gpt" in script

    @patch("vhdeployx.deployer.subprocess.run")
    def test_prepare_img_does_nothing(self, mock_run):
        _prepare_disk(1, ImageFormat.IMG)
        mock_run.assert_not_called()
