# AndroidMirror 📱→💻

Mirror your Android display to your laptop in **windowed mode** via USB-C — with full touch control, adjustable quality, and a clean GUI.

---

## How It Works

```
Android Device
     │
     │  USB-C cable (USB Debugging)
     │
  ADB (Android Debug Bridge)
     │
  scrcpy / ffplay  ──►  Windowed Display on Laptop
```

- **ADB** creates a communication channel over USB to your Android device  
- **scrcpy** (recommended) pushes a tiny server APK to your Android, captures the display in H.264 video, and streams it back — rendered in a native window on your laptop  
- **ffplay** (fallback) uses `adb exec-out screenrecord` to pipe a raw H.264 stream into a video player window  
- Touch and keyboard events from your laptop are forwarded back to Android (scrcpy only)

---

## Requirements

| Tool | Role | Install |
|------|------|---------|
| **Python 3.8+** | Runs the GUI | [python.org](https://python.org) |
| **ADB** | USB bridge | [Platform Tools](https://developer.android.com/tools/releases/platform-tools) |
| **scrcpy** *(recommended)* | Screen mirror engine | [github.com/Genymobile/scrcpy](https://github.com/Genymobile/scrcpy) |
| **ffmpeg + ffplay** *(fallback)* | Video stream fallback | [ffmpeg.org](https://ffmpeg.org/download.html) |

### Quick Install (scrcpy + ADB)

**Windows**
```powershell
winget install Genymobile.scrcpy
winget install Google.PlatformTools
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt update && sudo apt install scrcpy adb
```

**macOS**
```bash
brew install scrcpy android-platform-tools
```

---

## Android Setup (One-Time)

1. **Settings → About Phone** — tap **Build Number** 7 times  
2. **Settings → Developer Options** — enable **USB Debugging**  
3. Connect your phone to the laptop via **USB-C cable**  
4. On your phone: tap **Allow** when asked about USB Debugging  
5. Verify connection: `adb devices` (your device serial should appear)

---

## Running

```bash
# Check dependencies first
python setup.py

# Launch the app
python main.py
```

---

## GUI Features

| Setting | Description |
|---------|-------------|
| **Device list** | Auto-scans every 5 s — select your device |
| **Resolution** | Max height in px (480 / 720 / 1080 / 1440 / 2160) |
| **Bitrate** | Video quality (2M–24M) |
| **FPS** | Frame rate cap (24 / 30 / 60 / 120) |
| **Always on top** | Mirror window stays above other windows |
| **Show touches** | Visualise tap points on Android screen |
| **Turn off Android screen** | Phone screen goes dark while mirroring |
| **No audio** | Video-only (lower latency) |
| **Window position & size** | Pixel-precise windowed placement |
| **Quick presets** | One-click position presets |

---

## Keyboard Shortcuts (scrcpy window)

| Key | Action |
|-----|--------|
| `Ctrl+H` | Home button |
| `Ctrl+B` | Back button |
| `Ctrl+S` | App switcher |
| `Ctrl+P` | Power button |
| `Ctrl+N` | Notifications |
| `Ctrl+M` | Menu |
| `Ctrl+↑/↓` | Volume up/down |
| `Ctrl+Z` | Turn screen on/off |
| `Ctrl+F` | Toggle fullscreen |
| `MOD+x` | Expand notification panel |

---

## Troubleshooting

**Device not showing up**
- Check USB-C cable supports data (not charge-only)
- Re-enable USB Debugging on phone
- Run `adb kill-server && adb start-server`
- Try a different USB port

**`adb: command not found`**
- Add Platform Tools to your PATH  
- Windows: `setx PATH "%PATH%;C:\platform-tools"` then restart terminal

**Black screen / no video**
- Accept the USB Debugging prompt on the phone
- Check phone isn't locked; unlock and try again
- Lower resolution/bitrate if on a slow USB hub

**`scrcpy: command not found`**
- Install scrcpy (see above) — the app will fall back to ffplay if available

**High latency**
- Set bitrate to 4M–8M, FPS to 30
- Disable audio: check "No audio"
- Use a direct USB-C port, not a hub

---

## Architecture

```
android_mirror.py
├── MirrorSettings     ← dataclass for all config, persisted to ~/.android_mirror_settings.json
├── MirrorSession      ← wraps scrcpy or ffplay subprocess in a background thread
│   ├── _build_scrcpy_cmd()   ← maps settings → scrcpy CLI flags
│   └── _build_ffplay_cmd()   ← maps settings → adb | ffplay pipeline
└── AndroidMirrorApp   ← tkinter GUI
    ├── Environment panel   ← checks ADB / scrcpy / ffmpeg availability
    ├── Device panel        ← auto-refreshes ADB device list
    ├── Settings panel      ← resolution, bitrate, FPS, toggles
    └── Window panel        ← position & size, quick presets
```

---

## License

MIT — free to use, modify, and distribute.
