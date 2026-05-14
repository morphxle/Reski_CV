"""Ringwert aus Zentrum-Abstand (normalisiert auf Scheibenradius)."""

from __future__ import annotations

import math
from typing import Sequence


def ring_from_distance(
    dx: float,
    dy: float,
    center_x: float,
    center_y: float,
    max_radius: float,
    ring_fractions: Sequence[float],
) -> int:
    """
    ring_fractions: aufsteigende Grenzen 0..1 relativ zum Außenradius.
    Rückgabe: Ring 10 (Mitte) bis 1 (Außen), 0 = außerhalb / nicht treffbar.
    """
    dist = math.hypot(dx - center_x, dy - center_y)
    if max_radius <= 0:
        return 0
    t = dist / max_radius
    if t > ring_fractions[-1]:
        return 0
    # innerster Ring: t <= ring_fractions[0] -> höchster Wert
    n = len(ring_fractions)
    for i, frac in enumerate(ring_fractions):
        if t <= frac:
            return n - i
    return 0
