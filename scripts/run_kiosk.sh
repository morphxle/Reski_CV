#!/usr/bin/env bash
# Startet die Anwendung mit Display-/Energie-Settings und ausgeblendeter Maus.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export SCHUSS_CFG="${SCHUSS_CFG:-$ROOT/config/default_config.yaml}"
# X11-Energieoptionen (harmlose Fehler ignorieren)
if [[ -n "${DISPLAY:-}" ]]; then
  "$ROOT/scripts/configure_display_power.sh" || true
fi
if command -v unclutter >/dev/null 2>&1; then
  pkill unclutter 2>/dev/null || true
  unclutter -idle 0 -root &
fi
exec "$ROOT/venv/bin/python" "$ROOT/main.py"
