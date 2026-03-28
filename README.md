# Screen Recorder

Eigener Bildschirmrecorder mit pixelgenauer Bereichsauswahl, Audio-Aufnahme und GUI.

## Voraussetzungen

- **Python 3.9+** — [python.org/downloads](https://www.python.org/downloads/)
- **ffmpeg** — für Video-Encoding, muss im PATH liegen
  ```
  winget install ffmpeg
  ```

## Installation & Start

Doppelklick auf `start.bat` — installiert automatisch alle Dependencies und startet die App.

Oder manuell:

```bash
pip install -r requirements.txt
python screen_recorder.py
```

## Features

| Feature | Beschreibung |
|---------|-------------|
| **Pixelgenaue Größe** | Breite/Höhe numerisch eingeben (z.B. 1920×1080) |
| **Drag-Overlay** | Bereich per Maus auf abgedunkeltem Screenshot auswählen |
| **Audio** | Mikrofon-Aufnahme mit Geräteauswahl |
| **FPS** | 15 / 24 / 30 / 60 fps |
| **Formate** | MP4, MKV, AVI |
| **Dark UI** | Übersichtliche GUI mit Status-Anzeige |

## Architektur

```
screen_recorder.py
├── RegionSelector    — Fullscreen-Overlay zum Bereich aufziehen
├── AudioRecorder     — Mic-Aufnahme via sounddevice → WAV
├── VideoRecorder     — mss Screen-Capture → ffmpeg Pipe (libx264)
└── RecorderApp       — tkinter GUI + Orchestrierung
```

**Recording-Pipeline:**
1. `mss` grabbt Frames im gewählten Bereich mit Ziel-FPS
2. Raw BGRA-Frames werden per stdin-Pipe an `ffmpeg` gestreamt
3. Audio wird parallel via `sounddevice` in eine temp WAV geschrieben
4. Nach Stopp: Video + Audio werden per `ffmpeg -c:v copy` zusammengemuxed

## System-Audio aufnehmen

Für System-Audio (Desktop-Sound) unter Windows:

1. **Stereo Mix aktivieren:** Rechtsklick auf Lautsprecher-Icon → Sounds → Aufnahme → Rechtsklick → "Deaktivierte Geräte anzeigen" → "Stereo Mix" aktivieren
2. Oder **Virtual Audio Cable** installieren (z.B. VB-Audio Virtual Cable)
3. Das Gerät dann im Recorder als Audio-Quelle auswählen
