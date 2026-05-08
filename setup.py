#!/usr/bin/env python3
"""
AndroidMirror Setup & Dependency Checker
Run this first: python setup.py
"""

import sys
import platform
import shutil

OS = platform.system()  # Windows / Linux / Darwin

CYAN  = "\033[96m"
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
RESET = "\033[0m"
BOLD  = "\033[1m"

def print_banner():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════╗
║       AndroidMirror  Setup           ║
╚══════════════════════════════════════╝{RESET}
""")

def check(name: str) -> bool:
    found = shutil.which(name) is not None
    icon  = f"{GREEN}✔{RESET}" if found else f"{RED}✘{RESET}"
    print(f"  {icon}  {name:<12}  {'Found' if found else 'NOT FOUND'}")
    return found

def install_guide(tool: str):
    guides = {
        "adb": {
            "Windows": "winget install Google.PlatformTools  OR  https://developer.android.com/tools/releases/platform-tools",
            "Linux":   "sudo apt install adb    (Debian/Ubuntu)\n         sudo pacman -S android-tools  (Arch)",
            "Darwin":  "brew install android-platform-tools",
        },
        "scrcpy": {
            "Windows": "winget install Genymobile.scrcpy  OR  https://github.com/Genymobile/scrcpy/releases",
            "Linux":   "sudo apt install scrcpy    (Debian/Ubuntu)\n         sudo snap install scrcpy",
            "Darwin":  "brew install scrcpy",
        },
        "ffmpeg": {
            "Windows": "winget install Gyan.FFmpeg  OR  https://ffmpeg.org/download.html",
            "Linux":   "sudo apt install ffmpeg",
            "Darwin":  "brew install ffmpeg",
        },
    }
    if tool in guides:
        method = guides[tool].get(OS, guides[tool].get("Linux", "See project website"))
        print(f"\n  {YELLOW}Install {tool}:{RESET}")
        print(f"    {method}")

def main():
    print_banner()

    print(f"{BOLD}Checking Python version...{RESET}")
    major, minor = sys.version_info[:2]
    if major < 3 or minor < 8:
        print(f"  {RED}✘  Python 3.8+ required (you have {major}.{minor}){RESET}")
        sys.exit(1)
    print(f"  {GREEN}✔  Python {major}.{minor}{RESET}\n")

    print(f"{BOLD}Checking required tools...{RESET}")
    adb_ok    = check("adb")
    scrcpy_ok = check("scrcpy")
    ffmpeg_ok = check("ffmpeg") and check("ffplay")

    print()

    if not adb_ok:
        print(f"{RED}✘  ADB is REQUIRED.{RESET}")
        install_guide("adb")

    if not scrcpy_ok:
        print(f"{YELLOW}⚠  scrcpy not found (recommended for best quality).{RESET}")
        install_guide("scrcpy")
        if not ffmpeg_ok:
            print(f"{YELLOW}⚠  ffmpeg/ffplay also not found (needed as fallback).{RESET}")
            install_guide("ffmpeg")
    else:
        print(f"{GREEN}✔  scrcpy found — best mirroring quality available!{RESET}")

    print()

    # Android setup steps
    print(f"{BOLD}Android Setup Steps:{RESET}")
    steps = [
        "Go to Settings → About Phone",
        "Tap 'Build Number' 7 times to enable Developer Options",
        "Go to Settings → Developer Options",
        "Enable 'USB Debugging'",
        "Connect your phone to the laptop via USB-C",
        "When prompted on your phone, tap 'Allow' for USB Debugging",
        "Run 'adb devices' in terminal — your device serial should appear",
    ]
    for i, step in enumerate(steps, 1):
        print(f"  {CYAN}{i}.{RESET} {step}")

    print()

    if adb_ok and (scrcpy_ok or ffmpeg_ok):
        print(f"{GREEN}{BOLD}All set! Run the app:{RESET}")
        print(f"  python android_mirror.py\n")
    else:
        print(f"{YELLOW}Install missing tools above, then run:{RESET}")
        print(f"  python android_mirror.py\n")

if __name__ == "__main__":
    main()
