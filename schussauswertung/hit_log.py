"""Optionales Protokoll der Treffer (Koordinaten + Ring) als JSON Lines."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def append_hit_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def hit_payload(x: float, y: float, ring: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    p: dict[str, Any] = {
        "ts": time.time(),
        "x": round(x, 2),
        "y": round(y, 2),
        "ring": int(ring),
    }
    if extra:
        p.update(extra)
    return p
