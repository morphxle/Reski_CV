"""HDMI-Vollbild: Scheibe links, Trefferliste rechts, Kreis-Markierungen."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Hit:
    x: float
    y: float
    ring: int


def _draw_panel(
    panel: np.ndarray,
    hits: Deque[Hit],
    status_lines: list[str],
) -> None:
    panel[:] = (24, 24, 24)
    y = 28
    cv2.putText(
        panel,
        "Letzte Treffer",
        (12, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (240, 240, 240),
        1,
        cv2.LINE_AA,
    )
    y += 36
    # Neueste zuerst anzeigen
    for i, h in enumerate(reversed(list(hits))):
        line = f"{i + 1}. Ring {h.ring}  ({h.x:.0f},{h.y:.0f})"
        cv2.putText(
            panel,
            line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )
        y += 26
        if y > panel.shape[0] - 80:
            break
    y = max(y + 10, panel.shape[0] - 110)
    for sl in status_lines:
        cv2.putText(
            panel,
            sl[:48],
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (180, 200, 180),
            1,
            cv2.LINE_AA,
        )
        y += 22


def draw_hit_overlay(
    warped_bgr: np.ndarray,
    hits: Iterable[Hit],
    newest_color: Tuple[int, int, int] = (0, 0, 255),
    older_color: Tuple[int, int, int] = (255, 0, 0),
) -> np.ndarray:
    out = warped_bgr.copy()
    lst = list(hits)
    for idx, h in enumerate(lst):
        is_newest = idx == len(lst) - 1
        col = newest_color if is_newest else older_color
        r = 14 if is_newest else 10
        cv2.circle(out, (int(round(h.x)), int(round(h.y))), r, col, 2 if not is_newest else 3)
        if is_newest:
            cv2.circle(out, (int(round(h.x)), int(round(h.y))), 3, newest_color, -1)
    return out


def build_composite(
    warped_bgr: np.ndarray,
    hits: Deque[Hit],
    panel_width: int,
    status_lines: Optional[list[str]] = None,
) -> np.ndarray:
    h, w = warped_bgr.shape[:2]
    panel = np.zeros((h, panel_width, 3), dtype=np.uint8)
    _draw_panel(panel, hits, status_lines or [])
    left = draw_hit_overlay(warped_bgr, hits)
    return np.hstack([left, panel])


def setup_fullscreen_window(window_name: str) -> None:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty(
            window_name,
            cv2.WND_PROP_FULLSCREEN,
            cv2.WINDOW_FULLSCREEN,
        )
    except Exception:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
