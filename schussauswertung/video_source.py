"""Videoquelle: RTSP (Betrieb) oder lokale Datei (DEV_MODE für VM / Tests)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import cv2

from schussauswertung.rtsp_source import open_rtsp


def is_dev_mode() -> bool:
    v = os.environ.get("DEV_MODE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def open_capture(rtsp_url: str, dev_video_path: str | Path) -> cv2.VideoCapture:
    """
    Öffnet RTSP oder bei DEV_MODE=1 eine Videodatei (Schleife: siehe read_frame_looped).
    Zusätzliche Datei: Umgebungsvariable DEV_VIDEO_PATH (überschreibt dev_video_path).
    """
    if is_dev_mode():
        override = os.environ.get("DEV_VIDEO_PATH", "").strip()
        path = Path(override) if override else Path(dev_video_path)
        if not path.is_file():
            raise RuntimeError(
                f"DEV_MODE: Videodatei nicht gefunden: {path.resolve()} "
                "(DEV_VIDEO_PATH setzen oder dev_video_path in der Konfiguration / test_video.mp4)"
            )
        resolved = str(path.resolve())
        cap = cv2.VideoCapture(resolved, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap = cv2.VideoCapture(resolved)
        if not cap.isOpened():
            raise RuntimeError(f"DEV_MODE: Öffnen fehlgeschlagen: {resolved}")
        return cap
    return open_rtsp(rtsp_url)


def read_frame_looped(cap: cv2.VideoCapture) -> tuple[bool, Any]:
    """
    Liest ein Frame; bei Dateiende im DEV_MODE springt die Wiedergabe an den Anfang.
    """
    ok, frame = cap.read()
    if ok and frame is not None:
        return True, frame
    if not is_dev_mode():
        return False, None
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    except Exception:
        pass
    ok2, frame2 = cap.read()
    return (True, frame2) if ok2 and frame2 is not None else (False, None)
