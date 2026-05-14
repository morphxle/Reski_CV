#!/usr/bin/env bash
# Installation auf Raspberry Pi OS (Debian-basiert): Systempakete + venv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Bitte nicht als root ausführen; das Skript nutzt sudo für apt."
  exit 1
fi

echo "[install] APT-Pakete…"
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-dev \
  python3-pip \
  build-essential \
  cmake \
  pkg-config \
  libatlas-base-dev \
  ffmpeg \
  libavcodec-dev \
  libavformat-dev \
  libswscale-dev \
  libv4l-dev \
  v4l-utils \
  libgtk-3-dev \
  libjpeg-dev \
  libpng-dev \
  libtiff-dev \
  libx264-dev \
  libxvidcore-dev \
  x11-xserver-utils \
  unclutter \
  xdotool

echo "[install] Python venv…"
python3 -m venv "$ROOT/venv"
# shellcheck disable=SC1090
source "$ROOT/venv/bin/activate"
pip install --upgrade pip wheel
pip install -r "$ROOT/requirements.txt"

chmod +x "$ROOT/scripts/configure_display_power.sh" "$ROOT/scripts/run_kiosk.sh" "$ROOT/web_server.py" 2>/dev/null || true

echo "[install] Fertig."
echo "Konfiguration: $ROOT/config/default_config.yaml (rtsp_url anpassen)"
echo "Start (manuell): $ROOT/scripts/run_kiosk.sh"
echo "Web-UI: $ROOT/venv/bin/python $ROOT/web_server.py  →  http://<pi-ip>:8080"
echo "Systemd: sudo cp $ROOT/systemd/schussauswertung.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now schussauswertung.service"
echo "Web Systemd: sudo cp $ROOT/systemd/schussauswertung-web.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now schussauswertung-web.service"
echo "Autostart-Desktop: cp $ROOT/autostart/schussauswertung.desktop ~/.config/autostart/  (Pfade in der Datei anpassen)"
