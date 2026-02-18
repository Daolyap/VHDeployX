"""Deployment engine – orchestrates image-to-disk deployment.

Each supported image format has its own ``_deploy_*`` helper that shells out
to the appropriate Windows tool (DISM, diskpart, PowerShell, etc.).  On
non-Windows systems the helpers raise ``RuntimeError`` so the GUI can display
a clear message.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from vhdeployx.disk import DiskInfo, clean_disk
from vhdeployx.formats import ImageFormat, ImageInfo

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]  # (percent, message)


class DeploymentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DeploymentResult:
    status: DeploymentStatus
    message: str


class Deployer:
    """High-level deployment controller."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._status = DeploymentStatus.IDLE
        self._thread: threading.Thread | None = None

    @property
    def status(self) -> DeploymentStatus:
        with self._lock:
            return self._status

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._status == DeploymentStatus.RUNNING

    def cancel(self) -> None:
        self._cancel.set()

    # -- public API -------------------------------------------------------

    def deploy(
        self,
        image: ImageInfo,
        target_disk: DiskInfo,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Start the deployment in a background thread.

        *progress_cb* is called from the worker thread with ``(percent, msg)``.
        """
        if self.is_running:
            raise RuntimeError("A deployment is already in progress")
        self._cancel.clear()
        with self._lock:
            self._status = DeploymentStatus.RUNNING
        self._thread = threading.Thread(
            target=self._run,
            args=(image, target_disk, progress_cb),
            daemon=True,
        )
        self._thread.start()

    def _run(
        self,
        image: ImageInfo,
        target_disk: DiskInfo,
        progress_cb: ProgressCallback | None,
    ) -> None:
        def _progress(pct: int, msg: str) -> None:
            if progress_cb:
                progress_cb(pct, msg)

        try:
            _progress(0, "Starting deployment…")
            _ensure_windows()

            _progress(5, f"Cleaning disk {target_disk.index}…")
            if self._cancel.is_set():
                with self._lock:
                    self._status = DeploymentStatus.CANCELLED
                _progress(0, "Cancelled")
                return
            clean_disk(target_disk.index)

            _progress(10, "Preparing disk…")
            _prepare_disk(target_disk.index, image.format)

            if self._cancel.is_set():
                with self._lock:
                    self._status = DeploymentStatus.CANCELLED
                _progress(0, "Cancelled")
                return

            _progress(20, f"Deploying {image.format.value.upper()} image…")
            _deploy_image(image, target_disk.index, _progress)

            with self._lock:
                self._status = DeploymentStatus.SUCCESS
            _progress(100, "Deployment completed successfully")
        except Exception as exc:
            logger.exception("Deployment failed")
            with self._lock:
                self._status = DeploymentStatus.FAILED
            _progress(0, f"Error: {exc}")


# -- internal helpers -----------------------------------------------------


def _ensure_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError(
            "Image deployment requires Windows (DISM / diskpart)"
        )


def _escape_ps_path(path: object) -> str:
    """Escape a path for use in a PowerShell single-quoted string."""
    return str(path).replace("'", "''")


def _run_robocopy_ps(ps_command: str, *, timeout: int = 3600) -> None:
    """Run a PowerShell command that uses robocopy, with proper exit code handling.

    Robocopy exit codes 0-7 indicate success; 8+ indicate failure.
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_command],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode is not None and result.returncode >= 8:
        logger.error(
            "PowerShell/robocopy exited with code %s. stdout=%s stderr=%s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
        raise subprocess.CalledProcessError(
            returncode=result.returncode,
            cmd=result.args,
            output=result.stdout,
            stderr=result.stderr,
        )


def _prepare_disk(disk_index: int, fmt: ImageFormat) -> None:
    """Partition and format the target disk according to *fmt*."""
    if fmt in (ImageFormat.WIM, ImageFormat.ISO):
        # Create GPT with EFI System + primary NTFS
        script = (
            f"select disk {disk_index}\n"
            "convert gpt\n"
            "create partition efi size=260\n"
            "format fs=fat32 quick label=System\n"
            "assign letter=S\n"
            "create partition primary\n"
            "format fs=ntfs quick label=Windows\n"
            "assign letter=W\n"
        )
    elif fmt in (ImageFormat.VHD, ImageFormat.VHDX):
        # Single NTFS partition for VHD expansion
        script = (
            f"select disk {disk_index}\n"
            "convert gpt\n"
            "create partition efi size=260\n"
            "format fs=fat32 quick label=System\n"
            "assign letter=S\n"
            "create partition primary\n"
            "format fs=ntfs quick label=OS\n"
            "assign letter=W\n"
        )
    else:
        # IMG / raw – no partitioning, raw write
        return

    subprocess.run(
        ["diskpart"],
        input=script,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def _deploy_image(
    image: ImageInfo,
    disk_index: int,
    progress: ProgressCallback,
) -> None:
    """Dispatch to the appropriate deployment handler."""
    handlers = {
        ImageFormat.WIM: _deploy_wim,
        ImageFormat.VHD: _deploy_vhd,
        ImageFormat.VHDX: _deploy_vhd,
        ImageFormat.ISO: _deploy_iso,
        ImageFormat.IMG: _deploy_img,
    }
    handler = handlers.get(image.format)
    if handler is None:
        raise ValueError(f"No handler for format {image.format}")
    handler(image, disk_index, progress)


def _deploy_wim(
    image: ImageInfo, disk_index: int, progress: ProgressCallback
) -> None:
    """Apply a WIM image using DISM."""
    progress(30, "Applying WIM image with DISM…")
    subprocess.run(
        [
            "dism",
            "/Apply-Image",
            f"/ImageFile:{image.path}",
            "/Index:1",
            "/ApplyDir:W:\\",
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        check=True,
    )
    progress(80, "Creating boot files…")
    subprocess.run(
        ["bcdboot", "W:\\Windows", "/s", "S:", "/f", "UEFI"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    progress(95, "WIM deployment complete")


def _deploy_vhd(
    image: ImageInfo, disk_index: int, progress: ProgressCallback
) -> None:
    """Expand a VHD/VHDX to a physical disk via PowerShell."""
    progress(30, "Mounting VHD image…")
    vhd_path = _escape_ps_path(image.path)
    ps = (
        f"$vhdPath = '{vhd_path}'; "
        "$ErrorActionPreference = 'Stop'; "
        "try { "
        "$vhd = Mount-VHD -Path $vhdPath -PassThru -ReadOnly; "
        "$disk = $vhd | Get-Disk; "
        "$parts = $disk | Get-Partition | Where-Object { $_.Type -ne 'Reserved' }; "
        "foreach ($p in $parts) { "
        "  if ($p.AccessPaths -and $p.AccessPaths.Count -gt 0) { "
        "    $vol = $p | Get-Volume; "
        "    if ($vol.FileSystemType -eq 'NTFS') { "
        "      $src = $p.AccessPaths[0]; "
        "      robocopy $src W:\\ /E /COPYALL /DCOPY:DAT /R:1 /W:1; "
        "      if ($LASTEXITCODE -ge 8) { throw \"robocopy failed with exit code $LASTEXITCODE\" } "
        "    } "
        "  } "
        "} "
        "} finally { "
        "Dismount-VHD -Path $vhdPath "
        "}"
    )
    _run_robocopy_ps(ps)
    progress(80, "Creating boot files…")
    subprocess.run(
        ["bcdboot", "W:\\Windows", "/s", "S:", "/f", "UEFI"],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    progress(95, "VHD deployment complete")


def _deploy_iso(
    image: ImageInfo, disk_index: int, progress: ProgressCallback
) -> None:
    """Mount an ISO and copy contents (typically a Windows install media)."""
    progress(30, "Mounting ISO…")
    iso_path = _escape_ps_path(image.path)
    ps = (
        f"$isoPath = '{iso_path}'; "
        "$ErrorActionPreference = 'Stop'; "
        "try { "
        "$iso = Mount-DiskImage -ImagePath $isoPath -PassThru; "
        "$drive = ($iso | Get-Volume).DriveLetter; "
        '$src = "${drive}:\\"; '
        "robocopy $src W:\\ /E /R:1 /W:1; "
        "$robocopyExit = $LASTEXITCODE; "
        "} finally { "
        "Dismount-DiskImage -ImagePath $isoPath "
        "}; "
        "if ($robocopyExit -ge 8) { exit $robocopyExit } else { exit 0 }"
    )
    _run_robocopy_ps(ps)
    progress(80, "Setting up boot configuration…")
    try:
        subprocess.run(
            ["bcdboot", "W:\\Windows", "/s", "S:", "/f", "UEFI"],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    except subprocess.CalledProcessError:
        logger.warning(
            "bcdboot failed – the ISO may not contain a bootable Windows installation"
        )
    progress(95, "ISO deployment complete")


def _deploy_img(
    image: ImageInfo, disk_index: int, progress: ProgressCallback
) -> None:
    """Write a raw IMG file directly to the disk using PowerShell streams."""
    progress(30, "Writing raw image to disk…")
    img_path = _escape_ps_path(image.path)
    ps = (
        "$ErrorActionPreference = 'Stop'; "
        f"$src = [System.IO.File]::OpenRead('{img_path}'); "
        "try { "
        f"$dst = [System.IO.File]::OpenWrite('\\\\.\\PhysicalDrive{disk_index}'); "
        "try { "
        "$buf = New-Object byte[] (1MB); "
        "while (($n = $src.Read($buf, 0, $buf.Length)) -gt 0) { "
        "  $dst.Write($buf, 0, $n) "
        "} "
        "} finally { $dst.Dispose() } "
        "} finally { $src.Dispose() }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=7200,
        check=True,
    )
    progress(95, "Raw image write complete")
