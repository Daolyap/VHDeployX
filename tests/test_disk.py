"""Tests for vhdeployx.disk – disk enumeration helpers."""

import platform
from unittest.mock import patch

import pytest

from vhdeployx.disk import DiskInfo, _format_size, clean_disk, list_disks


class TestFormatSize:
    @pytest.mark.parametrize(
        "size, expected",
        [
            (0, "0.0 B"),
            (512, "512.0 B"),
            (1024, "1.0 KB"),
            (1048576, "1.0 MB"),
            (1073741824, "1.0 GB"),
            (1099511627776, "1.0 TB"),
        ],
    )
    def test_format_size(self, size: int, expected: str):
        assert _format_size(size) == expected


class TestDiskInfo:
    def test_label(self):
        d = DiskInfo(
            index=0,
            name="Samsung SSD",
            size_bytes=256_000_000_000,
            size_display="238.4 GB",
            media_type="SSD",
            partitions=3,
        )
        assert d.label == "Disk 0: Samsung SSD (238.4 GB)"


class TestListDisks:
    def test_returns_list_on_linux(self):
        # On non-Windows the stub returns an empty list
        if platform.system() != "Windows":
            assert list_disks() == []


class TestCleanDisk:
    def test_raises_on_non_windows(self):
        if platform.system() != "Windows":
            with pytest.raises(RuntimeError, match="Windows"):
                clean_disk(0)
