"""Gemeinsames Datei-Logging (parallel lesbar, z. B. unter Parallels Shared Folder)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def configure_logging() -> Path:
    """
    Konsole + rotierende Datei logs/schussauswertung.log.
    Optional: SCHUSS_LOGFILE=/abs/pfad/anderes.log (sonst relativ zum Projektroot).
    """
    root = _project_root()
    raw = os.environ.get("SCHUSS_LOGFILE", "").strip()
    log_path = Path(raw) if raw else root / "logs" / "schussauswertung.log"
    if not log_path.is_absolute():
        log_path = root / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    fh = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logging.basicConfig(level=logging.INFO, handlers=[sh, fh], force=True)
    return log_path
