#!/usr/bin/env python3
"""
Schießstand-Trefferauswertung: RTSP oder DEV_MODE-Video, Perspektive, Differencing, HDMI-Vollbild.

Umgebung:
  DEV_MODE=1        lokale Datei statt RTSP (Pfad: DEV_VIDEO_PATH oder config dev_video_path)
  SCHUSS_HW_DECODE=1  (nur aarch64) optional h264 v4l2m2m über FFmpeg — bei Fehlern deaktivieren

Kalibrierung wird in data/coords.json (oder calibration_file in YAML) gespeichert, inkl. Scheibenmitte.

Tastatur:
  c  Kalibrierung (4 Ecken auf Rohbild, Reihenfolge TL, TR, BR, BL)
  r  Trefferliste leeren
  b  Aktuelles entzerrtes Bild als neue Referenz (Hintergrund)
  s  Referenzbild dauerhaft speichern
  q  Beenden (Referenz wird gespeichert)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Deque, Optional, Tuple

import cv2
import numpy as np

from schussauswertung.calibration import Calibration, load_calibration, save_calibration
from schussauswertung.config_loader import load_config
from schussauswertung.detector import detect_impact
from schussauswertung.display import Hit, build_composite, setup_fullscreen_window
from schussauswertung.hit_log import append_hit_log, hit_payload
from schussauswertung.log_setup import configure_logging
from schussauswertung.platform_hw import apply_platform_capture_env, log_platform_summary
from schussauswertung.perspective import warp_frame
from schussauswertung.scoring import ring_from_distance
from schussauswertung.video_source import is_dev_mode, open_capture, read_frame_looped


CALIB_LABELS_DE = [
    "Ecke 1/4: oben-links",
    "Ecke 2/4: oben-rechts",
    "Ecke 3/4: unten-rechts",
    "Ecke 4/4: unten-links",
]


def _maybe_start_unclutter() -> None:
    if shutil.which("unclutter"):
        try:
            subprocess.Popen(
                ["unclutter", "-idle", "0", "-root"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def _load_reference_gray(path: Path, shape_wh: tuple[int, int]) -> Optional[np.ndarray]:
    if not path.is_file():
        return None
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    w, h = shape_wh
    if img.shape[1] != w or img.shape[0] != h:
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    return img


def _save_reference_gray(path: Path, gray: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), gray)


def _window_to_image_xy(
    window_name: str,
    x_win: int,
    y_win: int,
    img_w: int,
    img_h: int,
) -> Tuple[float, float]:
    """Mappt Mausposition (Fenster) auf Originalbildkoordinaten bei skalierter Anzeige."""
    r = cv2.getWindowImageRect(window_name)
    rx, ry, rw, rh = int(r[0]), int(r[1]), int(r[2]), int(r[3])
    if rw <= 1 or rh <= 1:
        return float(x_win), float(y_win)
    x_in = (x_win - rx) * img_w / float(rw)
    y_in = (y_win - ry) * img_h / float(rh)
    return float(x_in), float(y_in)


class CalibState:
    def __init__(self) -> None:
        self.active = False
        self.points: list[tuple[float, float]] = []

    def reset(self) -> None:
        self.active = False
        self.points.clear()

    def start(self) -> None:
        self.active = True
        self.points.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description="Schussauswertung HDMI/RTSP")
    parser.add_argument(
        "--config",
        default=os.environ.get("SCHUSS_CFG"),
        help="Pfad zu YAML-Konfiguration (oder Umgebungsvariable SCHUSS_CFG)",
    )
    args = parser.parse_args()
    apply_platform_capture_env()
    configure_logging()
    cfg = load_config(args.config)
    log_platform_summary(is_dev_mode())

    rtsp_url = str(cfg["rtsp_url"])
    dev_video_path = str(cfg.get("dev_video_path", "test_video.mp4"))
    warp_w, warp_h = int(cfg["warp_size"][0]), int(cfg["warp_size"][1])
    ring_fractions = list(cfg["ring_fractions"])
    diff_threshold = int(cfg["diff_threshold"])
    min_blob_area = int(cfg["min_blob_area"])
    morph_kernel = int(cfg["morph_kernel"])
    cooldown_frames = int(cfg["cooldown_frames"])
    panel_width = int(cfg["panel_width"])
    window_name = str(cfg["window_name"])
    cal_path = Path(str(cfg["calibration_file"]))
    ref_path = Path(str(cfg["reference_file"]))
    hits_log_path = Path(str(cfg["hits_log_file"]))

    max_radius = min(warp_w, warp_h) * 0.5

    cap = open_capture(rtsp_url, dev_video_path)
    cal: Optional[Calibration] = load_calibration(cal_path)

    hits: Deque[Hit] = deque(maxlen=10)
    cooldown = 0
    calib = CalibState()

    last_raw_shape: Tuple[int, int] = (1, 1)
    last_gray: Optional[np.ndarray] = None
    reference_gray: Optional[np.ndarray] = None
    paused_reference_update = False

    _maybe_start_unclutter()
    setup_fullscreen_window(window_name)

    def status_lines() -> list[str]:
        lines = [
            "[c] Kalibrierung",
            "[r] Treffer reset",
            "[b] Referenz aus Bild",
            "[s] Referenz speichern",
            "[q] Beenden",
        ]
        if calib.active:
            idx = len(calib.points)
            lab = CALIB_LABELS_DE[idx] if idx < len(CALIB_LABELS_DE) else "Speichern…"
            lines = [f"KALIBRIERUNG: {lab}", "Mausklick setzt Ecke"]
        elif cal is None:
            lines.insert(0, "WARN: keine Kalibrierung")
        if is_dev_mode():
            lines.append("DEV_MODE: lokale Videodatei")
        return lines

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        nonlocal cal, reference_gray, paused_reference_update
        if event != cv2.EVENT_LBUTTONDOWN or not calib.active:
            return
        if len(calib.points) >= 4:
            return
        ih, iw = last_raw_shape[1], last_raw_shape[0]
        xi, yi = _window_to_image_xy(window_name, x, y, iw, ih)
        calib.points.append((xi, yi))
        if len(calib.points) == 4:
            dcx = (warp_w - 1) * 0.5
            dcy = (warp_h - 1) * 0.5
            cal = Calibration(
                points=[(p[0], p[1]) for p in calib.points],
                disc_center_warp=(dcx, dcy),
            )
            save_calibration(cal_path, cal, warp_size=(warp_w, warp_h))
            calib.reset()
            paused_reference_update = False
            reference_gray = None

    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        ok, frame = read_frame_looped(cap)
        if not ok or frame is None:
            time.sleep(0.05)
            continue

        fh, fw = frame.shape[:2]
        last_raw_shape = (fw, fh)

        if cal is None or calib.active:
            disp = frame.copy()
            if calib.active:
                for i, (px, py) in enumerate(calib.points):
                    cv2.circle(disp, (int(round(px)), int(round(py))), 8, (0, 255, 255), -1)
                    cv2.putText(
                        disp,
                        str(i + 1),
                        (int(round(px)) + 10, int(round(py)) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 255),
                        2,
                    )
                idx = len(calib.points)
                hint = CALIB_LABELS_DE[idx] if idx < len(CALIB_LABELS_DE) else "Speichern…"
                cv2.putText(
                    disp,
                    hint,
                    (20, 48),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
            else:
                cv2.putText(
                    disp,
                    "Taste [c] fuer Kalibrierung (4 Ecken)",
                    (20, 48),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 200, 255),
                    2,
                    cv2.LINE_AA,
                )
            cv2.imshow(window_name, disp)
        else:
            warped = warp_frame(frame, cal, warp_w, warp_h)
            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            last_gray = gray

            if reference_gray is None:
                loaded = _load_reference_gray(ref_path, (warp_w, warp_h))
                if loaded is not None:
                    reference_gray = loaded
                else:
                    reference_gray = gray.copy()

            if cooldown > 0:
                cooldown -= 1

            if not paused_reference_update:
                disc_cx = (warp_w - 1) * 0.5
                disc_cy = (warp_h - 1) * 0.5
                if cal is not None and cal.disc_center_warp is not None:
                    disc_cx, disc_cy = cal.disc_center_warp
                res = detect_impact(
                    gray,
                    reference_gray,
                    diff_threshold=diff_threshold,
                    min_blob_area=min_blob_area,
                    morph_kernel=morph_kernel,
                )
                if res.center is not None and cooldown == 0:
                    cx, cy = res.center
                    ring = ring_from_distance(
                        cx,
                        cy,
                        disc_cx,
                        disc_cy,
                        max_radius,
                        ring_fractions,
                    )
                    hits.append(Hit(x=cx, y=cy, ring=ring))
                    append_hit_log(
                        hits_log_path,
                        hit_payload(cx, cy, ring, {"warp": [warp_w, warp_h]}),
                    )
                    cooldown = cooldown_frames
                    reference_gray = gray.copy()

            composite = build_composite(
                warped,
                hits,
                panel_width=panel_width,
                status_lines=status_lines(),
            )
            cv2.imshow(window_name, composite)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            if reference_gray is not None:
                _save_reference_gray(ref_path, reference_gray)
            break
        if key == ord("r"):
            hits.clear()
            cooldown = 0
        if key == ord("b") and cal is not None and last_gray is not None and not calib.active:
            reference_gray = last_gray.copy()
        if key == ord("s") and reference_gray is not None:
            _save_reference_gray(ref_path, reference_gray)
        if key == ord("c"):
            calib.start()
            paused_reference_update = True

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
