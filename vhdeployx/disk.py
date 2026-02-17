"""Disk enumeration and management helpers.

On Windows the module shells out to PowerShell / diskpart.  On other
platforms it provides stub data so the GUI can still be developed and tested.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass


@dataclass
class DiskInfo:
    """Describes a physical disk available on the system."""

    index: int
    name: str
    size_bytes: int
    size_display: str
    media_type: str
    partitions: int

    @property
    def label(self) -> str:
        return f"Disk {self.index}: {self.name} ({self.size_display})"


def _format_size(size_bytes: int) -> str:
    """Return a human-friendly size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"


def list_disks() -> list[DiskInfo]:
    """Return the list of physical disks on the current system."""
    if platform.system() == "Windows":
        return _list_disks_windows()
    return _list_disks_stub()


def _list_disks_windows() -> list[DiskInfo]:
    """Use PowerShell ``Get-Disk`` to enumerate disks."""
    ps_script = (
        "Get-Disk | Select-Object Number, FriendlyName, Size, MediaType, "
        "NumberOfPartitions | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        disks: list[DiskInfo] = []
        for item in data:
            size = int(item.get("Size", 0))
            disks.append(
                DiskInfo(
                    index=int(item["Number"]),
                    name=str(item.get("FriendlyName", "Unknown")),
                    size_bytes=size,
                    size_display=_format_size(size),
                    media_type=str(item.get("MediaType", "Unknown")),
                    partitions=int(item.get("NumberOfPartitions", 0)),
                )
            )
        return disks
    except Exception:
        return []


def _list_disks_stub() -> list[DiskInfo]:
    """Return empty list on non-Windows (no disks to deploy to)."""
    return []


def clean_disk(disk_index: int) -> subprocess.CompletedProcess[str]:
    """Run diskpart ``clean`` on the specified disk (Windows only).

    Raises ``RuntimeError`` on non-Windows systems.
    """
    if platform.system() != "Windows":
        raise RuntimeError("Disk cleaning is only supported on Windows")

    script = f"select disk {disk_index}\nclean\n"
    return subprocess.run(
        ["diskpart"],
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )
