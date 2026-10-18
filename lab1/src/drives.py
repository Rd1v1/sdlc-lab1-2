"""Сведения о дисках и свободном пространстве."""
from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path
from typing import Any


def list_drives() -> list[dict[str, Any]]:
    roots = []
    if hasattr(os, "listdrives"):
        roots = os.listdrives()
    elif os.name == "nt":
        roots = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]
    else:
        roots = ["/"]
    drives = []
    for root in roots:
        try:
            usage = shutil.disk_usage(root)
            item: dict[str, Any] = {
                "path": root,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "available_bytes": usage.free,
            }
            if os.name == "nt":
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
                item["drive_type"] = {
                    2: "removable",
                    3: "fixed",
                    4: "network",
                    5: "optical",
                    6: "ramdisk",
                }.get(drive_type, "unknown")
                volume_name = ctypes.create_unicode_buffer(261)
                file_system = ctypes.create_unicode_buffer(261)
                ctypes.windll.kernel32.GetVolumeInformationW(
                    root, volume_name, len(volume_name), None, None, None, file_system, len(file_system)
                )
                item["volume_label"] = volume_name.value
                item["file_system"] = file_system.value
            drives.append(item)
        except OSError:
            continue
    return drives
