#!/usr/bin/env bash
#
# Deaktiviert Bildschirmschoner, DPMS-Standby und Leerlauf-Dimming für
# typische Raspberry-Pi-Desktop-Umgebungen (X11 + optional Wayland/GNOME).
# Als normaler Benutzer ausführen (nicht root), damit Session-Dienste greifen.
#
set -euo pipefail

echo "[configure_display_power] X11 (falls DISPLAY gesetzt)…"
if [[ -n "${DISPLAY:-}" ]] && command -v xset >/dev/null 2>&1; then
  xset s off 2>/dev/null || true
  xset s noblank 2>/dev/null || true
  # DPMS komplett aus (kein HDMI-Standby über X11)
  xset -dpms 2>/dev/null || true
fi

if command -v xscreensaver-command >/dev/null 2>&1; then
  xscreensaver-command -exit 2>/dev/null || true
fi

echo "[configure_display_power] GNOME/gsettings (falls vorhanden)…"
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
  gsettings set org.gnome.desktop.screensaver lock-enabled false 2>/dev/null || true
  gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
  gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' 2>/dev/null || true
fi

echo "[configure_display_power] systemd user: maskiere ggf. leerzeuger@… (optional, Fehler ignorieren)"
systemctl --user mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

echo "[configure_display_power] Fertig."
