"""Speichern und Laden der 4 Eckpunkte für die Perspektivkorrektur (coords.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass
class Calibration:
    """Vier Bildpunkte der Scheibe in Kamera-Koordinaten (Reihenfolge: TL, TR, BR, BL)."""

    points: list[tuple[float, float]]
    disc_center_warp: Optional[tuple[float, float]] = None

    def __post_init__(self) -> None:
        if len(self.points) != 4:
            raise ValueError("Genau vier Eckpunkte erforderlich.")

    def to_list(self) -> list[list[float]]:
        return [[float(x), float(y)] for x, y in self.points]

    @classmethod
    def from_list(
        cls,
        pts: Sequence[Sequence[float]],
        disc_center_warp: Optional[tuple[float, float]] = None,
    ) -> "Calibration":
        return cls(
            points=[(float(p[0]), float(p[1])) for p in pts],
            disc_center_warp=disc_center_warp,
        )


def _parse_center(data: dict) -> Optional[tuple[float, float]]:
    raw = data.get("disc_center_warp") or data.get("center")
    if not raw or len(raw) != 2:
        return None
    return float(raw[0]), float(raw[1])


def _load_file(p: Path) -> Optional["Calibration"]:
    if not p.is_file():
        return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and len(data) == 4:
        return Calibration.from_list(data)
    if not isinstance(data, dict):
        return None
    pts = data.get("corners") or data.get("points") or data.get("coords")
    if not pts or len(pts) != 4:
        return None
    center = _parse_center(data)
    return Calibration.from_list(pts, disc_center_warp=center)


def load_calibration(path: str | Path) -> Optional[Calibration]:
    """Lädt coords.json / calibration.json; Fallback auf calibration.json neben coords.json."""
    p = Path(path)
    candidates: list[Path] = [p]
    if p.name == "coords.json":
        candidates.append(p.parent / "calibration.json")
    for cand in candidates:
        cal = _load_file(cand)
        if cal is not None:
            return cal
    return None


def save_calibration(
    path: str | Path,
    cal: Calibration,
    *,
    warp_size: Optional[tuple[int, int]] = None,
) -> None:
    """Schreibt corners + optional Scheibenmitte und warp_size (für coords.json)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"corners": cal.to_list()}
    if warp_size is not None:
        ww, wh = int(warp_size[0]), int(warp_size[1])
        cx, cy = (ww - 1) * 0.5, (wh - 1) * 0.5
        payload["disc_center_warp"] = [cx, cy]
        payload["warp_size"] = [ww, wh]
    elif cal.disc_center_warp is not None:
        payload["disc_center_warp"] = [cal.disc_center_warp[0], cal.disc_center_warp[1]]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
