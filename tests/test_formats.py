"""Tests for vhdeployx.formats – format detection, validation, and metadata."""

import tempfile
from pathlib import Path

import pytest

from vhdeployx.formats import (
    EXTENSION_MAP,
    FORMAT_DESCRIPTIONS,
    ImageFormat,
    detect_format,
    get_image_info,
    supported_extensions,
    validate_signature,
)


# -- detect_format ---------------------------------------------------------

class TestDetectFormat:
    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("image.wim", ImageFormat.WIM),
            ("image.esd", ImageFormat.WIM),
            ("image.swm", ImageFormat.WIM),
            ("image.vhd", ImageFormat.VHD),
            ("image.vhdx", ImageFormat.VHDX),
            ("image.iso", ImageFormat.ISO),
            ("image.img", ImageFormat.IMG),
            ("image.raw", ImageFormat.IMG),
            ("IMAGE.WIM", ImageFormat.WIM),
            ("IMAGE.VHDX", ImageFormat.VHDX),
        ],
    )
    def test_known_extensions(self, filename: str, expected: ImageFormat):
        assert detect_format(filename) == expected

    @pytest.mark.parametrize("filename", ["file.txt", "data.bin", "archive.zip", "noext"])
    def test_unknown_extensions(self, filename: str):
        assert detect_format(filename) is None


# -- validate_signature ----------------------------------------------------

class TestValidateSignature:
    def test_wim_valid(self, tmp_path: Path):
        f = tmp_path / "test.wim"
        f.write_bytes(b"MSWIM\x00\x00\x00" + b"\x00" * 256)
        assert validate_signature(f, ImageFormat.WIM) is True

    def test_wim_invalid(self, tmp_path: Path):
        f = tmp_path / "test.wim"
        f.write_bytes(b"NOT_WIM_" + b"\x00" * 256)
        assert validate_signature(f, ImageFormat.WIM) is False

    def test_vhd_valid(self, tmp_path: Path):
        f = tmp_path / "test.vhd"
        f.write_bytes(b"conectix" + b"\x00" * 256)
        assert validate_signature(f, ImageFormat.VHD) is True

    def test_vhd_invalid(self, tmp_path: Path):
        f = tmp_path / "test.vhd"
        f.write_bytes(b"XXXXXXXX" + b"\x00" * 256)
        assert validate_signature(f, ImageFormat.VHD) is False

    def test_vhdx_valid(self, tmp_path: Path):
        f = tmp_path / "test.vhdx"
        f.write_bytes(b"vhdxfile" + b"\x00" * 256)
        assert validate_signature(f, ImageFormat.VHDX) is True

    def test_iso_valid(self, tmp_path: Path):
        f = tmp_path / "test.iso"
        # ISO magic at offset 0x8001
        data = b"\x00" * 0x8001 + b"CD001" + b"\x00" * 256
        f.write_bytes(data)
        assert validate_signature(f, ImageFormat.ISO) is True

    def test_iso_invalid(self, tmp_path: Path):
        f = tmp_path / "test.iso"
        f.write_bytes(b"\x00" * 0x8001 + b"XXXXX")
        assert validate_signature(f, ImageFormat.ISO) is False

    def test_img_always_valid(self, tmp_path: Path):
        f = tmp_path / "test.img"
        f.write_bytes(b"\x00" * 512)
        assert validate_signature(f, ImageFormat.IMG) is True

    def test_missing_file(self, tmp_path: Path):
        missing = tmp_path / "missing.wim"
        assert validate_signature(missing, ImageFormat.WIM) is False


# -- get_image_info --------------------------------------------------------

class TestGetImageInfo:
    def test_valid_wim(self, tmp_path: Path):
        f = tmp_path / "install.wim"
        content = b"MSWIM\x00\x00\x00" + b"\x00" * 512
        f.write_bytes(content)
        info = get_image_info(f)
        assert info.format == ImageFormat.WIM
        assert info.valid_signature is True
        assert info.size_bytes == len(content)
        assert "WIM" in info.description

    def test_unsupported_extension(self, tmp_path: Path):
        f = tmp_path / "data.txt"
        f.write_bytes(b"hello")
        with pytest.raises(ValueError, match="Unsupported"):
            get_image_info(f)

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            get_image_info(tmp_path / "missing.vhd")


# -- supported_extensions --------------------------------------------------

class TestSupportedExtensions:
    def test_returns_sorted_list(self):
        exts = supported_extensions()
        assert exts == sorted(exts)
        assert all(e.startswith(".") for e in exts)

    def test_includes_main_formats(self):
        exts = supported_extensions()
        for ext in [".wim", ".vhd", ".vhdx", ".iso", ".img"]:
            assert ext in exts


# -- IMAGE_FORMAT enum covers descriptions --------------------------------

class TestFormatDescriptions:
    def test_all_formats_described(self):
        for fmt in ImageFormat:
            assert fmt in FORMAT_DESCRIPTIONS
