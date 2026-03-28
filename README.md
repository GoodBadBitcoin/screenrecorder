# Screen Recorder

Custom screen recorder with pixel-exact region selection, audio capture, and GUI.

## Requirements

- **Python 3.9+** — [python.org/downloads](https://www.python.org/downloads/)
- **ffmpeg** — for video encoding, must be in PATH

## Installation & Start

Double-click `install.bat` to install all dependencies (including ffmpeg), then run `start.bat` to launch.

Or manually:

```bash
pip install -r requirements.txt
python screen_recorder.py
```

## Features

| Feature | Description |
|---------|-------------|
| **Pixel-exact size** | Enter width/height numerically (e.g. 1920×1080) |
| **Drag overlay** | Select area by dragging on a darkened screenshot |
| **Audio** | Microphone recording with device selection |
| **FPS** | 15 / 24 / 30 / 60 fps |
| **Formats** | MP4, MKV, AVI |
| **Language** | Switch between English and German |
| **Dark UI** | Clean GUI with status display |

## Architecture

```
screen_recorder.py
├── RegionSelector    — Fullscreen overlay for drawing a capture area
├── RegionOverlay     — Draggable/resizable border showing the recording region
├── AudioRecorder     — Mic capture via sounddevice → WAV
├── VideoRecorder     — mss screen capture → ffmpeg pipe (libx264)
└── RecorderApp       — tkinter GUI + orchestration
```

**Recording pipeline:**
1. `mss` grabs frames in the selected region at the target FPS
2. Raw BGRA frames are piped via stdin to `ffmpeg`
3. Audio is recorded in parallel via `sounddevice` into a temp WAV
4. After stop: video + audio are muxed with `ffmpeg -c:v copy`

## Recording System Audio

To capture desktop audio on Windows:

1. **Enable Stereo Mix:** Right-click speaker icon → Sounds → Recording → Right-click → "Show Disabled Devices" → Enable "Stereo Mix"
2. Or install **Virtual Audio Cable** (e.g. VB-Audio Virtual Cable)
3. Select the device as audio source in the recorder
