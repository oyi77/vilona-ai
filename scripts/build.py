import subprocess
import sys
from pathlib import Path


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
        "app_server.py",
    ]
    return subprocess.run(cmd, check=True).returncode


if __name__ == "__main__":
    try:
        build_windows()
        print("Windows build complete: build/Vilona AI-v2.exe")
    except Exception as e:
        print(f"Windows build failed: {e}")
