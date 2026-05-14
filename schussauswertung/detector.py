"""Schusserkennung per Frame-Differencing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class DetectionResult:
    center: Optional[Tuple[float, float]]
    mask: np.ndarray


def detect_impact(
    current_gray: np.ndarray,
    reference_gray: np.ndarray,
    diff_threshold: int,
    min_blob_area: int,
    morph_kernel: int,
) -> DetectionResult:
    """Vergleicht aktuelles Graustufenbild mit Referenz; liefert Schwerpunkt größter Region."""
    if current_gray.shape != reference_gray.shape:
        raise ValueError("Referenz und aktuelles Bild müssen gleiche Größe haben.")
    diff = cv2.absdiff(current_gray, reference_gray)
    _, th = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)
    k = max(3, morph_kernel | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    th = cv2.dilate(th, kernel, iterations=1)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for c in contours:
        a = cv2.contourArea(c)
        if a < min_blob_area or a <= best_area:
            continue
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"]
        best = (cx, cy)
        best_area = a

    return DetectionResult(center=best, mask=th)
