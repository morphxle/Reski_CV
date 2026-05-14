"""Perspektivkorrektur (Homographie)."""

from __future__ import annotations

import cv2
import numpy as np

from schussauswertung.calibration import Calibration


def warp_frame(
    frame_bgr: np.ndarray,
    cal: Calibration,
    warp_w: int,
    warp_h: int,
) -> np.ndarray:
    src = np.array(cal.points, dtype=np.float32)
    dst = np.array(
        [
            [0.0, 0.0],
            [float(warp_w - 1), 0.0],
            [float(warp_w - 1), float(warp_h - 1)],
            [0.0, float(warp_h - 1)],
        ],
        dtype=np.float32,
    )
    h = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(
        frame_bgr,
        h,
        (warp_w, warp_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
