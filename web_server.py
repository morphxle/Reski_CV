#!/usr/bin/env python3
"""
Web-Oberfläche: MJPEG-Vorschau (niedrige FPS) + alle YAML-Einstellungen.

Start: python web_server.py [--config pfad/zur.yaml]

Hinweis: Zweite Videoquelle zum HDMI-Prozess. Mit DEV_MODE=1 wie bei main.py wird dieselbe
lokale Datei genutzt (DEV_VIDEO_PATH oder dev_video_path in der YAML). Manche Kameras erlauben
nur einen RTSP-Client.
Die HDMI-Anwendung (main.py) lädt die Konfiguration beim Start; nach Speichern
hier ggf. main.py neu starten, damit alle Werte greifen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

import cv2
import numpy as np
import uvicorn
import yaml
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates

from schussauswertung.calibration import Calibration, load_calibration, save_calibration
from schussauswertung.config_loader import config_file_path, load_config, save_config
from schussauswertung.log_setup import configure_logging
from schussauswertung.platform_hw import apply_platform_capture_env, log_platform_summary
from schussauswertung.perspective import warp_frame
from schussauswertung.video_source import is_dev_mode, open_capture, read_frame_looped

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _rel_to_project(path_val: str, root: Path) -> str:
    p = Path(path_val)
    if not p.is_absolute():
        return str(path_val)
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


def _placeholder_jpeg(message: str = "Kein Bild") -> bytes:
    img = np.zeros((360, 480, 3), dtype=np.uint8)
    img[:] = (32, 32, 32)
    y = 180
    for line in message.split("\n")[:3]:
        cv2.putText(
            img,
            line[:42],
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )
        y += 28
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    return buf.tobytes() if ok else b""


def _parse_ring_fractions(text: str) -> list[float]:
    text = text.strip()
    if not text:
        raise ValueError("Ringgrenzen dürfen nicht leer sein.")
    parts = re.split(r"[\s,;]+", text)
    vals = [float(p) for p in parts if p]
    if len(vals) < 1:
        raise ValueError("Mindestens eine Ringgrenze angeben.")
    return vals


def _draw_target_overlay(
    bgr: np.ndarray,
    warp_w: int,
    warp_h: int,
    cal: Calibration,
    ring_fractions: list[float],
) -> None:
    """Zeichnet Mittelpunkt + Ringkreise (laut YAML) auf das entzerrte Vorschau-Bild."""
    if cal.disc_center_warp is not None:
        cx, cy = cal.disc_center_warp
    else:
        cx = (warp_w - 1) * 0.5
        cy = (warp_h - 1) * 0.5
    max_r = min(warp_w, warp_h) * 0.5
    pt = (int(round(cx)), int(round(cy)))
    cv2.drawMarker(
        bgr,
        pt,
        (0, 255, 160),
        markerType=cv2.MARKER_CROSS,
        markerSize=22,
        thickness=2,
        lineType=cv2.LINE_AA,
    )
    col_ring = (60, 200, 255)
    for frac in ring_fractions:
        r = int(max(2, round(float(frac) * max_r)))
        cv2.circle(bgr, pt, r, col_ring, 1, lineType=cv2.LINE_AA)
    cv2.putText(
        bgr,
        "Ringe (YAML) + Mitte",
        (8, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (230, 230, 230),
        1,
        cv2.LINE_AA,
    )


class PreviewRunner:
    """Eigenständiger RTSP-Thread, niedrige FPS, JPEG für MJPEG."""

    def __init__(self, cfg_path: Path) -> None:
        self.cfg_path = cfg_path
        self._lock = threading.Lock()
        self._jpeg = _placeholder_jpeg("Starte Vorschau…")
        self._stop = threading.Event()
        self._reload = threading.Event()

    def get_jpeg(self) -> bytes:
        with self._lock:
            return self._jpeg

    def notify_reload(self) -> None:
        self._reload.set()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        while not self._stop.is_set():
            try:
                cfg = load_config(self.cfg_path)
            except Exception as exc:
                self._set_jpeg(_placeholder_jpeg(f"Config:\n{exc}"))
                time.sleep(2.0)
                continue

            web = cfg.get("web") or {}
            fps = float(web.get("preview_fps", 4))
            scale = float(web.get("stream_scale", 0.45))
            mode = str(web.get("preview_mode", "warped")).lower()
            rtsp_url = str(cfg["rtsp_url"])
            dev_video_path = str(cfg.get("dev_video_path", "test_video.mp4"))
            warp_w, warp_h = int(cfg["warp_size"][0]), int(cfg["warp_size"][1])
            cal_path = Path(str(cfg["calibration_file"]))
            cal = load_calibration(cal_path)
            ring_fractions = [float(x) for x in (cfg.get("ring_fractions") or [])]

            if cap is not None:
                cap.release()
                cap = None
            try:
                cap = open_capture(rtsp_url, dev_video_path)
            except Exception as exc:
                self._set_jpeg(_placeholder_jpeg(f"Video:\n{exc}"))
                self._wait_reload_or_stop(2.0)
                continue

            period = 1.0 / max(0.25, min(fps, 30.0))
            last_emit = 0.0

            while not self._stop.is_set():
                if self._reload.is_set():
                    self._reload.clear()
                    break

                ok, frame = read_frame_looped(cap)
                if not ok or frame is None:
                    time.sleep(0.03)
                    continue

                now = time.monotonic()
                if now - last_emit < period:
                    time.sleep(0.005)
                    continue
                last_emit = now

                if mode == "warped" and cal is not None:
                    disp = warp_frame(frame, cal, warp_w, warp_h)
                    if ring_fractions:
                        _draw_target_overlay(disp, warp_w, warp_h, cal, ring_fractions)
                else:
                    disp = frame
                    if mode == "warped" and cal is None:
                        cv2.putText(
                            disp,
                            "Keine Kalibrierung (Rohbild)",
                            (16, 40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.9,
                            (0, 200, 255),
                            2,
                            cv2.LINE_AA,
                        )

                h, w = disp.shape[:2]
                sc = max(0.1, min(scale, 1.0))
                nw = max(120, int(round(w * sc)))
                nh = max(120, int(round(h * sc)))
                small = cv2.resize(disp, (nw, nh), interpolation=cv2.INTER_AREA)
                ok2, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
                if ok2:
                    self._set_jpeg(buf.tobytes())

            if cap is not None:
                cap.release()
                cap = None

    def _set_jpeg(self, data: bytes) -> None:
        with self._lock:
            self._jpeg = data

    def _wait_reload_or_stop(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            if self._reload.is_set():
                self._reload.clear()
                return
            time.sleep(0.05)


def _deep_merge_web(base: dict[str, Any], form_web: dict[str, Any]) -> None:
    w = base.get("web")
    if not isinstance(w, dict):
        w = {}
    w = dict(w)
    w.update(form_web)
    base["web"] = w


def build_app(cfg_path: Path) -> tuple[FastAPI, PreviewRunner]:
    runner = PreviewRunner(cfg_path)
    app = FastAPI(title="Schussauswertung Web")

    @app.exception_handler(HTTPException)
    async def _http_exc_handler(request: Request, exc: HTTPException) -> HTMLResponse:
        if exc.status_code == 403:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><meta charset=utf-8><title>Zugriff</title></head>"
                "<body style='font-family:sans-serif;background:#121418;color:#eee;padding:24px'>"
                "<p>Zugriff verweigert. Öffnen Sie die Seite mit dem korrekten <code>?token=…</code> "
                "Parameter (wie in der Konfiguration unter <code>web.access_token</code>).</p></body></html>",
                status_code=403,
            )
        return HTMLResponse(f"<pre>{exc.detail}</pre>", status_code=exc.status_code)

    def _expected_token() -> str:
        try:
            cfg = load_config(cfg_path)
            w = cfg.get("web") or {}
            return str(w.get("access_token") or "").strip()
        except Exception:
            return ""

    def _check_token(request: Request, form_token: Optional[str] = None) -> None:
        exp = _expected_token()
        if not exp:
            return
        q = request.query_params.get("token", "")
        if q == exp or (form_token and form_token == exp):
            return
        raise HTTPException(status_code=403, detail="Ungültiges oder fehlendes token")

    @app.on_event("startup")
    def _startup() -> None:
        apply_platform_capture_env()
        configure_logging()
        log_platform_summary(is_dev_mode())
        t = threading.Thread(target=runner.run, name="preview", daemon=True)
        t.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        runner.stop()
        runner.notify_reload()

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Any:
        _check_token(request)
        try:
            cfg = load_config(cfg_path)
        except Exception as exc:
            return HTMLResponse(f"<pre>Konfiguration: {exc}</pre>", status_code=500)
        root = cfg_path.resolve().parent.parent
        web = cfg.get("web") or {}
        ring_txt = "\n".join(str(x) for x in cfg.get("ring_fractions") or [])
        cal = None
        try:
            cal = load_calibration(Path(str(cfg["calibration_file"])))
        except Exception:
            pass
        cal_json = ""
        if cal is not None:
            blob: dict = {"corners": cal.to_list()}
            if cal.disc_center_warp is not None:
                blob["disc_center_warp"] = [cal.disc_center_warp[0], cal.disc_center_warp[1]]
            cal_json = json.dumps(blob, indent=2)
        tok = request.query_params.get("token", "")
        stream_src = "/stream" + (f"?token={quote_plus(tok)}" if tok else "")
        ctx = {
            "msg": request.query_params.get("msg", ""),
            "err": request.query_params.get("err", ""),
            "token": tok,
            "stream_src": stream_src,
            "rtsp_url": cfg.get("rtsp_url", ""),
            "warp_w": int(cfg.get("warp_size", [900, 900])[0]),
            "warp_h": int(cfg.get("warp_size", [900, 900])[1]),
            "ring_fractions": ring_txt,
            "diff_threshold": int(cfg.get("diff_threshold", 25)),
            "min_blob_area": int(cfg.get("min_blob_area", 80)),
            "morph_kernel": int(cfg.get("morph_kernel", 5)),
            "cooldown_frames": int(cfg.get("cooldown_frames", 15)),
            "panel_width": int(cfg.get("panel_width", 320)),
            "window_name": str(cfg.get("window_name", "Schussauswertung")),
            "data_dir": _rel_to_project(str(cfg.get("data_dir", "data")), root),
            "calibration_file": _rel_to_project(str(cfg.get("calibration_file", "data/coords.json")), root),
            "reference_file": _rel_to_project(str(cfg.get("reference_file", "data/reference.png")), root),
            "hits_log_file": _rel_to_project(str(cfg.get("hits_log_file", "data/hits.jsonl")), root),
            "dev_video_path": _rel_to_project(str(cfg.get("dev_video_path", "test_video.mp4")), root),
            "web_host": str(web.get("host", "0.0.0.0")),
            "web_port": int(web.get("port", 8080)),
            "preview_fps": float(web.get("preview_fps", 4)),
            "stream_scale": float(web.get("stream_scale", 0.45)),
            "preview_mode": str(web.get("preview_mode", "warped")),
            "access_token": str(web.get("access_token", "")),
            "calibration_json": cal_json,
        }
        return templates.TemplateResponse(request, "index.html", ctx)

    @app.get("/favicon.ico", include_in_schema=False)
    async def _favicon() -> Response:
        return Response(status_code=204)

    @app.get("/stream")
    async def stream(request: Request) -> StreamingResponse:
        _check_token(request)
        boundary = "schussframe"

        async def gen() -> Any:
            while True:
                chunk = runner.get_jpeg()
                yield (
                    b"--" + boundary.encode("ascii") + b"\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + chunk + b"\r\n"
                )
                try:
                    cfg = load_config(cfg_path)
                    web = cfg.get("web") or {}
                    fps = float(web.get("preview_fps", 4))
                except Exception:
                    fps = 4.0
                await asyncio.sleep(1.0 / max(0.25, min(fps, 30.0)))

        return StreamingResponse(
            gen(),
            media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        )

    @app.post("/save")
    async def save(
        request: Request,
        rtsp_url: str = Form(...),
        dev_video_path: str = Form(...),
        warp_w: int = Form(...),
        warp_h: int = Form(...),
        ring_fractions: str = Form(...),
        diff_threshold: int = Form(...),
        min_blob_area: int = Form(...),
        morph_kernel: int = Form(...),
        cooldown_frames: int = Form(...),
        panel_width: int = Form(...),
        window_name: str = Form(...),
        data_dir: str = Form(...),
        calibration_file: str = Form(...),
        reference_file: str = Form(...),
        hits_log_file: str = Form(...),
        web_host: str = Form(...),
        web_port: int = Form(...),
        preview_fps: float = Form(...),
        stream_scale: float = Form(...),
        preview_mode: str = Form(...),
        access_token: str = Form(""),
        calibration_json: str = Form(""),
        token: str = Form(""),
    ) -> RedirectResponse:
        _check_token(request, form_token=token)
        root = cfg_path.resolve().parent.parent
        try:
            rings = _parse_ring_fractions(ring_fractions)
            with open(cfg_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                raw = {}
            raw["rtsp_url"] = rtsp_url.strip()
            raw["dev_video_path"] = dev_video_path.strip() or "test_video.mp4"
            raw["warp_size"] = [int(warp_w), int(warp_h)]
            raw["ring_fractions"] = rings
            raw["diff_threshold"] = int(diff_threshold)
            raw["min_blob_area"] = int(min_blob_area)
            raw["morph_kernel"] = int(morph_kernel)
            raw["cooldown_frames"] = int(cooldown_frames)
            raw["panel_width"] = int(panel_width)
            raw["window_name"] = window_name.strip() or "Schussauswertung"
            raw["data_dir"] = data_dir.strip() or "data"
            raw["calibration_file"] = calibration_file.strip() or "data/coords.json"
            raw["reference_file"] = reference_file.strip() or "data/reference.png"
            raw["hits_log_file"] = hits_log_file.strip() or "data/hits.jsonl"
            pm = preview_mode.strip().lower()
            if pm not in ("warped", "raw"):
                pm = "warped"
            _deep_merge_web(
                raw,
                {
                    "host": web_host.strip() or "0.0.0.0",
                    "port": int(web_port),
                    "preview_fps": float(preview_fps),
                    "stream_scale": float(stream_scale),
                    "preview_mode": pm,
                    "access_token": access_token.strip(),
                },
            )
            save_config(cfg_path, raw)

            cj = calibration_json.strip()
            if cj:
                data = json.loads(cj)
                if isinstance(data, dict):
                    pts = data.get("corners") or data.get("points") or data.get("coords")
                    if not pts or len(pts) != 4:
                        raise ValueError("Kalibrierung: im JSON-Objekt »corners« mit 4 Punkten.")
                    center_raw = data.get("disc_center_warp") or data.get("center")
                    dc: Optional[tuple[float, float]] = None
                    if isinstance(center_raw, (list, tuple)) and len(center_raw) == 2:
                        dc = (float(center_raw[0]), float(center_raw[1]))
                    cal = Calibration.from_list(pts, disc_center_warp=dc)
                elif isinstance(data, list):
                    if len(data) != 4:
                        raise ValueError("Kalibrierung: genau 4 Punkte [[x,y], …] als JSON-Array.")
                    cal = Calibration.from_list(data)
                else:
                    raise ValueError("Kalibrierung: JSON-Array oder Objekt mit »corners«.")
                cal_abs = Path(raw["calibration_file"])
                if not cal_abs.is_absolute():
                    cal_abs = root / cal_abs
                save_calibration(cal_abs, cal, warp_size=(int(warp_w), int(warp_h)))

            runner.notify_reload()
        except Exception as exc:
            err = str(exc).replace("\n", " ")
            tok_q = f"&token={quote_plus(token)}" if token else ""
            return RedirectResponse(f"/?err={quote_plus(err)}{tok_q}", status_code=303)

        tok_out = access_token.strip() or token
        tok_q = f"&token={quote_plus(tok_out)}" if tok_out else ""
        return RedirectResponse(f"/?msg={quote_plus('Gespeichert.')}{tok_q}", status_code=303)

    return app, runner


def main() -> None:
    parser = argparse.ArgumentParser(description="Schussauswertung Web-UI")
    parser.add_argument("--config", default=os.environ.get("SCHUSS_CFG"), help="YAML-Konfiguration")
    args = parser.parse_args()
    cfg_path = config_file_path(args.config)
    if not cfg_path.is_file():
        raise SystemExit(f"Konfiguration nicht gefunden: {cfg_path}")

    cfg = load_config(cfg_path)
    web = cfg.get("web") or {}
    host = str(web.get("host", "0.0.0.0"))
    port = int(web.get("port", 8080))

    app, _runner = build_app(cfg_path)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
