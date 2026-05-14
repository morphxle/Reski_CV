"""Plattform-Erkennung (x86_64 / aarch64) und optionale FFmpeg-Capture-Umgebung."""

from __future__ import annotations

import logging
import os
import platform
from typing import Final

logger = logging.getLogger(__name__)

# Raspberry Pi und typische Desktop-VMs
ARCH_AARCH64: Final = "aarch64"
ARCH_X86_64: Final = "x86_64"


def machine_arch() -> str:
    m = platform.machine().lower()
    if m in ("amd64",):
        return ARCH_X86_64
    return m


def is_aarch64() -> bool:
    return machine_arch() == ARCH_AARCH64


def is_x86_64() -> bool:
    return machine_arch() == ARCH_X86_64


def apply_platform_capture_env() -> None:
    """
    Setzt OPENCV_FFMPEG_CAPTURE_OPTIONS nur, wenn noch nicht gesetzt.
    aarch64: TCP + Latenz; optional V4L2-m2m-HW mit SCHUSS_HW_DECODE=1.
    x86_64: TCP (Parallels / Desktop-VM).
    """
    if os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS"):
        return
    arch = machine_arch()
    if arch == ARCH_AARCH64:
        base = "rtsp_transport;tcp|max_delay;500000"
        if os.environ.get("SCHUSS_HW_DECODE", "").strip().lower() in ("1", "true", "yes", "on"):
            base += "|hwaccel;v4l2m2m"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = base
    else:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def log_platform_summary(dev_mode: bool) -> None:
    logger.info(
        "Plattform arch=%s system=%s dev_mode=%s ffmpeg_opts_set=%s",
        machine_arch(),
        platform.system(),
        dev_mode,
        bool(os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")),
    )
