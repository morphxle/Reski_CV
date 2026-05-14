"""Laden und Zusammenführen von YAML-Konfiguration."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

_REL_PATH_KEYS = frozenset(
    {"data_dir", "calibration_file", "reference_file", "hits_log_file", "dev_video_path"}
)


def config_file_path(path: str | Path | None = None) -> Path:
    base = Path(__file__).resolve().parent.parent
    return Path(path) if path else base / "config" / "default_config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = config_file_path(path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("Konfiguration muss ein YAML-Mapping sein.")
    root = cfg_path.resolve().parent.parent
    for key in _REL_PATH_KEYS:
        if key in cfg and cfg[key] and not os.path.isabs(str(cfg[key])):
            cfg[key] = str(root / str(cfg[key]))
    return cfg


def save_config(path: str | Path | None, cfg: dict[str, Any]) -> None:
    """Schreibt YAML; bekannte Pfade werden relativ zum Projektroot gespeichert."""
    cfg_path = config_file_path(path)
    root = cfg_path.resolve().parent.parent
    out = copy.deepcopy(cfg)
    for key in _REL_PATH_KEYS:
        if key not in out or not out[key]:
            continue
        val = str(out[key])
        if os.path.isabs(val) and val.startswith(str(root) + os.sep):
            out[key] = os.path.relpath(val, root)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
