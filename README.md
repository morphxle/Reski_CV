# Schussauswertung (OpenCV)

Trefferauswertung für einen Schießstand: **RTSP-/RTSPS-Kamera**, perspektivisch entzerrte Scheibe, **Frame-Differencing** zur Schusserkennung, **Ringwert** aus dem Abstand zur Scheibenmitte. **HDMI-Vollbild** mit Trefferliste und optional **Web-Oberfläche** (MJPEG-Vorschau + Einstellungen).

Zielplattform: **Raspberry Pi** (aarch64) oder **Desktop Linux** (z. B. Debian mit X11), Entwicklung z. B. mit `DEV_MODE` und lokaler Videodatei.

## Funktionen

- RTSP / **RTSPS** (TLS), inkl. typischer FFmpeg-Optionen für `rtsps://`
- Perspektivkorrektur über **4 Eckpunkte** (Maus), Speicherung in **`data/coords.json`**
- Schusserkennung per **Differenz** zum Referenzbild; Treffer in **`data/hits.jsonl`**
- HDMI: Vollbild, Trefferkreise (neueste / ältere), rechtes Panel mit den letzten 10 Treffern
- Web: niedrige FPS, **Ring-Overlay** im Modus „entzerrt“, Formular für YAML-Werte
- Optional: **Hardware-Decode** auf dem Pi (`SCHUSS_HW_DECODE`), Datei-Logging unter `logs/`

## Voraussetzungen

- Linux mit **X11** (OpenCV `imshow`; unter reinem Wayland ggf. XWayland nutzen)
- Python **3.10+** empfohlen
- Kamera liefert **H.264**-Stream (RTSP/RTSPS), oder lokale Datei für Tests

## Installation

```bash
chmod +x install.sh
./install.sh
```

Installiert Systempakete (u. a. FFmpeg, GTK, Build-Tools) und legt ein **`venv/`** mit Python-Abhängigkeiten an. Nicht als root ausführen (`sudo` nur für `apt`).

## Konfiguration

Standard: **`config/default_config.yaml`**

- **`rtsp_url`**: Stream-URL; bei Sonderzeichen in YAML **einfache Anführungszeichen** verwenden, z. B.  
  `rtsp_url: 'rtsps://192.168.10.1:7441/…?enableSrtp'`
- **`warp_size`**, **`ring_fractions`**, Schwellen für Differencing (`diff_threshold`, `min_blob_area`, …)
- **`web`**: `host`, `port`, `preview_fps`, optional **`access_token`** (Zugriff nur mit `?token=…`)

Eigener Konfigurationspfad:

```bash
export SCHUSS_CFG=/pfad/zur/konfig.yaml
```

Persistente Daten liegen unter **`data/`** (`coords.json`, `reference.png`, `hits.jsonl`). Beim Code-Update nur **`config/`** und **`data/`** nicht überschreiben, wenn die Einstellungen erhalten bleiben sollen (siehe Kommentar oben in der YAML).

## Umgebungsvariablen (Auswahl)

| Variable | Bedeutung |
|----------|-----------|
| `SCHUSS_CFG` | Pfad zur YAML-Konfiguration |
| `DEV_MODE=1` | Statt RTSP: lokale Datei (`DEV_VIDEO_PATH` oder `dev_video_path` in der YAML) |
| `DEV_VIDEO_PATH` | Überschreibt `dev_video_path` aus der YAML |
| `SCHUSS_HW_DECODE=1` | Nur **aarch64**: optional FFmpeg `v4l2m2m` (bei Problemen aus) |
| `SCHUSS_LOGFILE` | Eigenes Logfile; Standard: `logs/schussauswertung.log` |

## HDMI-Anwendung starten

```bash
source venv/bin/activate
./scripts/run_kiosk.sh
```

Oder direkt:

```bash
./venv/bin/python main.py --config config/default_config.yaml
```

### Tastatur (`main.py`)

| Taste | Aktion |
|-------|--------|
| `c` | Kalibrierung: 4 Ecken **TL → TR → BR → BL** (Rohbild) |
| `r` | Trefferliste leeren |
| `b` | Aktuelles entzerrtes Bild als neue Referenz |
| `s` | Referenz nach `data/reference.png` speichern |
| `q` | Beenden (speichert Referenz) |

## Web-Oberfläche

```bash
source venv/bin/activate
python web_server.py
```

Browser: **`http://<rechner-ip>:<web.port>/`** (Standard 8080). Zweiter RTSP-Client — manche Kameras erlauben nur einen Stream.

## Systemd / Autostart

Beispiel-Units: **`systemd/schussauswertung.service`**, **`systemd/schussauswertung-web.service`** — Pfade (`User`, `WorkingDirectory`, `ExecStart`) anpassen, dann:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now schussauswertung.service
```

Desktop-Autostart: **`autostart/schussauswertung.desktop`** nach `~/.config/autostart/` kopieren und `Exec=` prüfen.

## Logs

Schreibt nach **`logs/schussauswertung.log`** (rotierend), zusätzlich Konsolen-Ausgabe — siehe `schussauswertung/log_setup.py`.

## Projektstruktur (Kurz)

| Pfad | Rolle |
|------|--------|
| `main.py` | HDMI-Hauptschleife |
| `web_server.py` | FastAPI + MJPEG |
| `schussauswertung/` | Vision, Kalibrierung, Plattform, Videoquelle, … |
| `config/default_config.yaml` | Zentrale Konfiguration |
| `templates/index.html` | Web-UI |
| `scripts/` | Kiosk-Start, Display/Energie (xset, …) |

## Lizenz

Keine Lizenz im Repository hinterlegt — bei Bedarf ergänzen.
