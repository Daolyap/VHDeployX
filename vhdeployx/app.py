"""VHDeployX – tkinter desktop GUI for disk-image deployment."""

from __future__ import annotations

import logging
import os
import platform
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from vhdeployx.deployer import Deployer, DeploymentStatus
from vhdeployx.disk import DiskInfo, list_disks
from vhdeployx.formats import (
    FORMAT_DESCRIPTIONS,
    ImageFormat,
    ImageInfo,
    get_image_info,
    supported_extensions,
)

logger = logging.getLogger(__name__)

_PAD = {"padx": 8, "pady": 4}
_FILETYPES = [
    ("All supported images", " ".join(f"*{e}" for e in supported_extensions())),
    ("WIM / ESD / SWM", "*.wim *.esd *.swm"),
    ("VHD", "*.vhd"),
    ("VHDX", "*.vhdx"),
    ("ISO", "*.iso"),
    ("IMG / RAW", "*.img *.raw"),
    ("All files", "*.*"),
]


class VHDeployXApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("VHDeployX – Image Deployment Tool")
        self.geometry("720x560")
        self.minsize(620, 480)
        self.resizable(True, True)

        self._image_info: ImageInfo | None = None
        self._disks: list[DiskInfo] = []
        self._deployer = Deployer()

        self._build_ui()
        self._refresh_disks()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        # Menu bar
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Image…", command=self._browse_image)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- Source image section ----
        src_frame = ttk.LabelFrame(main, text="Source Image", padding=8)
        src_frame.pack(fill=tk.X, **_PAD)

        row = ttk.Frame(src_frame)
        row.pack(fill=tk.X)
        self._path_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._path_var, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4)
        )
        ttk.Button(row, text="Browse…", command=self._browse_image).pack(
            side=tk.RIGHT
        )

        self._info_var = tk.StringVar(value="No image selected")
        ttk.Label(src_frame, textvariable=self._info_var, foreground="gray").pack(
            anchor=tk.W, pady=(4, 0)
        )

        # ---- Target disk section ----
        dst_frame = ttk.LabelFrame(main, text="Target Disk", padding=8)
        dst_frame.pack(fill=tk.X, **_PAD)

        row2 = ttk.Frame(dst_frame)
        row2.pack(fill=tk.X)
        self._disk_var = tk.StringVar()
        self._disk_combo = ttk.Combobox(
            row2, textvariable=self._disk_var, state="readonly", width=50
        )
        self._disk_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(row2, text="Refresh", command=self._refresh_disks).pack(
            side=tk.RIGHT
        )

        self._disk_detail_var = tk.StringVar()
        ttk.Label(
            dst_frame, textvariable=self._disk_detail_var, foreground="gray"
        ).pack(anchor=tk.W, pady=(4, 0))

        self._disk_combo.bind("<<ComboboxSelected>>", self._on_disk_selected)

        # ---- Progress section ----
        prog_frame = ttk.LabelFrame(main, text="Progress", padding=8)
        prog_frame.pack(fill=tk.X, **_PAD)

        self._progress = ttk.Progressbar(prog_frame, length=400, mode="determinate")
        self._progress.pack(fill=tk.X)
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(prog_frame, textvariable=self._status_var).pack(
            anchor=tk.W, pady=(4, 0)
        )

        # ---- Log section ----
        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, **_PAD)

        self._log_text = tk.Text(log_frame, height=8, state="disabled", wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # ---- Buttons ----
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, **_PAD)

        self._deploy_btn = ttk.Button(
            btn_frame, text="Deploy", command=self._start_deploy
        )
        self._deploy_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self._cancel_btn = ttk.Button(
            btn_frame, text="Cancel", command=self._cancel_deploy, state="disabled"
        )
        self._cancel_btn.pack(side=tk.RIGHT)

    # -- actions -----------------------------------------------------------

    def _browse_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Disk Image", filetypes=_FILETYPES
        )
        if not path:
            return
        try:
            info = get_image_info(path)
        except (ValueError, FileNotFoundError) as exc:
            messagebox.showerror("Error", str(exc))
            return

        self._image_info = info
        self._path_var.set(str(info.path))
        sig = "valid" if info.valid_signature else "unverified"
        size_mb = info.size_bytes / (1024 * 1024)
        self._info_var.set(
            f"{info.description}  |  {size_mb:,.1f} MB  |  Signature: {sig}"
        )
        self._log(f"Loaded image: {info.path}")

    def _refresh_disks(self) -> None:
        self._disks = list_disks()
        labels = [d.label for d in self._disks]
        self._disk_combo["values"] = labels
        if labels:
            self._disk_combo.current(0)
            self._on_disk_selected()
        else:
            self._disk_var.set("")
            self._disk_detail_var.set(
                "No disks found"
                if platform.system() == "Windows"
                else "Disk listing requires Windows"
            )
        self._log(f"Refreshed disks: {len(self._disks)} found")

    def _on_disk_selected(self, _event: Any = None) -> None:
        idx = self._disk_combo.current()
        if 0 <= idx < len(self._disks):
            d = self._disks[idx]
            self._disk_detail_var.set(
                f"Type: {d.media_type}  |  Partitions: {d.partitions}"
            )

    def _start_deploy(self) -> None:
        if self._image_info is None:
            messagebox.showwarning("Warning", "Please select a source image first.")
            return
        idx = self._disk_combo.current()
        if idx < 0 or idx >= len(self._disks):
            messagebox.showwarning("Warning", "Please select a target disk.")
            return

        target = self._disks[idx]
        confirm = messagebox.askyesno(
            "Confirm Deployment",
            f"ALL DATA on {target.label} will be ERASED.\n\n"
            f"Image: {self._image_info.path.name}\n"
            f"Target: {target.label}\n\n"
            "Continue?",
        )
        if not confirm:
            return

        self._deploy_btn.config(state="disabled")
        self._cancel_btn.config(state="normal")
        self._progress["value"] = 0

        self._deployer.deploy(
            self._image_info, target, progress_cb=self._on_progress
        )
        self._poll_deployment()

    def _cancel_deploy(self) -> None:
        self._deployer.cancel()
        self._log("Cancellation requested…")

    def _on_progress(self, pct: int, msg: str) -> None:
        # Called from the worker thread – schedule on main thread
        self.after(0, self._apply_progress, pct, msg)

    def _apply_progress(self, pct: int, msg: str) -> None:
        self._progress["value"] = pct
        self._status_var.set(msg)
        self._log(msg)

    def _poll_deployment(self) -> None:
        if self._deployer.is_running:
            self.after(250, self._poll_deployment)
            return
        # finished
        self._deploy_btn.config(state="normal")
        self._cancel_btn.config(state="disabled")
        status = self._deployer.status
        if status == DeploymentStatus.SUCCESS:
            messagebox.showinfo("Done", "Deployment completed successfully!")
        elif status == DeploymentStatus.FAILED:
            messagebox.showerror("Failed", "Deployment failed. Check the log.")
        elif status == DeploymentStatus.CANCELLED:
            messagebox.showinfo("Cancelled", "Deployment was cancelled.")

    # -- log ---------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self._log_text.config(state="normal")
        self._log_text.insert(tk.END, msg + "\n")
        self._log_text.see(tk.END)
        self._log_text.config(state="disabled")

    # -- about -------------------------------------------------------------

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About VHDeployX",
            "VHDeployX v1.0.0\n\n"
            "Deploy VHDX, VHD, WIM, ISO, and IMG images to physical disks.\n\n"
            "Supported formats:\n"
            + "\n".join(f"  • {d}" for d in FORMAT_DESCRIPTIONS.values()),
        )
