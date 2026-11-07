"""
Build script for Vilona AI v2 - creates distributable executables.
Uses Nuitka for better performance and smaller output vs PyInstaller.
"""

import subprocess
import sys
import os
from pathlib import Path


def run(cmd, cwd=None):
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, check=True)
    return result.returncode


def build_windows():
    """Build Windows .exe using Nuitka"""
    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--output-filename=Vilona AI-v2.exe",
        "--output-dir=build",
        "--include-package=config",
        "--include-package=trading",
        "--include-package=agents",
        "--include-package=llm",
        "--include-package=ui",
        "--python-version=3.10",
        "app_server.py",
    ]
    return run(cmd)


def build_linux():
    """Build Linux executable using Nuitka"""
    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--output-filename=Vilona AI-v2-linux",
        "--output-dir=build",
        "--include-package=config",
        "--include-package=trading",
        "--include-package=agents",
        "--include-package=llm",
        "--include-package=ui",
        "app_server.py",
    ]
    return run(cmd)


def build_macos():
    """Build macOS executable using Nuitka"""
    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--macos-create-app-bundle",
        "--output-filename=Vilona AI-v2.app",
        "--output-dir=build",
        "--include-package=config",
        "--include-package=trading",
        "--include-package=agents",
        "--include-package=llm",
        "--include-package=ui",
        "app_server.py",
    ]
    return run(cmd)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in ("windows", "all"):
        try:
            build_windows()
            print("Windows build complete: build/Vilona AI-v2.exe")
        except Exception as e:
            print(f"Windows build failed: {e}")

    if target in ("linux", "all"):
        try:
            build_linux()
            print("Linux build complete: build/Vilona AI-v2-linux")
        except Exception as e:
            print(f"Linux build failed: {e}")

    if target in ("macos", "all"):
        try:
            build_macos()
            print("macOS build complete: build/Vilona AI-v2.app")
        except Exception as e:
            print(f"macOS build failed: {e}")
