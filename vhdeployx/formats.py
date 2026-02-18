"""Image format detection, validation, and metadata extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO


class ImageFormat(Enum):
    """Supported disk-image formats."""

    WIM = "wim"
    VHD = "vhd"
    VHDX = "vhdx"
    ISO = "iso"
    IMG = "img"


# Mapping from file extension to ImageFormat
EXTENSION_MAP: dict[str, ImageFormat] = {
    ".wim": ImageFormat.WIM,
    ".esd": ImageFormat.WIM,
    ".swm": ImageFormat.WIM,
    ".vhd": ImageFormat.VHD,
    ".vhdx": ImageFormat.VHDX,
    ".iso": ImageFormat.ISO,
    ".img": ImageFormat.IMG,
    ".raw": ImageFormat.IMG,
}

# Magic bytes used for format validation
_MAGIC = {
    ImageFormat.WIM: b"MSWIM\x00\x00\x00",
    ImageFormat.VHD: b"conectix",
    ImageFormat.VHDX: b"vhdxfile",
    ImageFormat.ISO: None,  # checked at offset 0x8001
}

_ISO_MAGIC = b"CD001"
_ISO_MAGIC_OFFSET = 0x8001

# Human-readable descriptions
FORMAT_DESCRIPTIONS: dict[ImageFormat, str] = {
    ImageFormat.WIM: "Windows Imaging Format (WIM/ESD/SWM)",
    ImageFormat.VHD: "Virtual Hard Disk (VHD)",
    ImageFormat.VHDX: "Virtual Hard Disk v2 (VHDX)",
    ImageFormat.ISO: "ISO 9660 Optical Disc Image",
    ImageFormat.IMG: "Raw Disk Image (IMG/RAW)",
}


@dataclass
class ImageInfo:
    """Metadata about a disk image file."""

    path: Path
    format: ImageFormat
    size_bytes: int
    valid_signature: bool
    description: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def detect_format(path: str | Path) -> ImageFormat | None:
    """Detect image format from file extension.

    Returns ``None`` when the extension is not recognised.
    """
    ext = Path(path).suffix.lower()
    return EXTENSION_MAP.get(ext)


def validate_signature(path: str | Path, fmt: ImageFormat) -> bool:
    """Return True if the file's magic bytes match *fmt*."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        with open(path, "rb") as fh:
            return _check_magic(fh, fmt)
    except OSError:
        return False


def _check_magic(fh: BinaryIO, fmt: ImageFormat) -> bool:
    if fmt == ImageFormat.ISO:
        try:
            fh.seek(_ISO_MAGIC_OFFSET)
            return fh.read(len(_ISO_MAGIC)) == _ISO_MAGIC
        except OSError:
            return False
    if fmt == ImageFormat.IMG:
        return True  # raw images have no magic header
    magic = _MAGIC.get(fmt)
    if magic is None:
        return False
    fh.seek(0)
    return fh.read(len(magic)) == magic


def get_image_info(path: str | Path) -> ImageInfo:
    """Build an ``ImageInfo`` for *path*.

    Raises ``ValueError`` when the file extension is not recognised.
    Raises ``FileNotFoundError`` when *path* does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    fmt = detect_format(path)
    if fmt is None:
        raise ValueError(f"Unsupported image format: {path.suffix}")
    valid = validate_signature(path, fmt)
    return ImageInfo(
        path=path,
        format=fmt,
        size_bytes=path.stat().st_size,
        valid_signature=valid,
        description=FORMAT_DESCRIPTIONS.get(fmt, ""),
    )


def supported_extensions() -> list[str]:
    """Return a sorted list of supported file extensions (with leading dot)."""
    return sorted(EXTENSION_MAP.keys())
