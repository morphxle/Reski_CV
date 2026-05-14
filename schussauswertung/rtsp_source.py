"""RTSP-Erfassung mit niedriger Pufferung (Raspberry Pi / FFmpeg)."""

from __future__ import annotations

import os

import cv2

# FFmpeg blockiert sonst u. a. „crypto“/„tls“ — nötig für RTSPS + SRTP
_RTSPS_WHITELIST = "file,http,https,tcp,tls,crypto,srtp,rtp,udp"


def _ensure_rtsps_ffmpeg_options(url: str) -> None:
    if not url.lower().startswith("rtsps:"):
        return
    cur = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
    if "protocol_whitelist" in cur:
        return
    prefix = f"protocol_whitelist;{_RTSPS_WHITELIST}"
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"{prefix}|{cur}" if cur else prefix


def open_rtsp(url: str) -> cv2.VideoCapture:
    _ensure_rtsps_ffmpeg_options(url)
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    # Reduziert interne Latenz (wirkt je nach OpenCV-Build unterschiedlich)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    if not cap.isOpened():
        raise RuntimeError(f"RTSP-Stream konnte nicht geöffnet werden: {url}")
    return cap
