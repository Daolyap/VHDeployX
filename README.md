# VHDeployX

Deploy VHDX, VHD, WIM, ISO, and IMG disk images to physical disks.

A Python desktop GUI application for administrators to deploy well-known image file formats to disks — for example applying a WIM as a ready-to-use OS, expanding a virtual hard disk to a physical drive, writing an ISO or raw IMG, and more.

## Supported Formats

| Format | Extensions | Description |
|--------|-----------|-------------|
| WIM | `.wim`, `.esd`, `.swm` | Windows Imaging Format – deployed via DISM |
| VHD | `.vhd` | Virtual Hard Disk – expanded to physical disk |
| VHDX | `.vhdx` | Virtual Hard Disk v2 – expanded to physical disk |
| ISO | `.iso` | ISO 9660 optical disc image – contents copied to disk |
| IMG | `.img`, `.raw` | Raw disk image – written directly to disk |

## Requirements

- **Python 3.10+**
- **Windows** (deployment operations use DISM, diskpart, and PowerShell)
- **Administrator privileges** (required for disk operations)

## Installation

```bash
pip install .
```

## Usage

Launch the GUI:

```bash
python -m vhdeployx
```

Or via the console entry point:

```bash
vhdeployx
```

1. **Select a source image** — Browse for a WIM, VHD, VHDX, ISO, or IMG file.
2. **Select a target disk** — Choose from the list of detected physical disks.
3. **Deploy** — Confirm and start the deployment. Progress and logs are shown in real time.

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Project Structure

```
vhdeployx/
├── __init__.py      # Package metadata
├── __main__.py      # Entry point
├── app.py           # tkinter desktop GUI
├── deployer.py      # Deployment orchestration engine
├── disk.py          # Disk enumeration and management
└── formats.py       # Image format detection and validation
tests/
├── test_deployer.py # Deployer tests
├── test_disk.py     # Disk module tests
└── test_formats.py  # Format detection tests
```
