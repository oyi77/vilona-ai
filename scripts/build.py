import subprocess
import sys
import os
from pathlib import Path

def build():
    """Build standalone executable using Nuitka"""
    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)

    system = sys.platform
    if system == "win32":
        filename = "Vilona-AI.exe"
    elif system == "darwin":
        filename = "Vilona-AI.app"
    else:
        filename = "Vilona-AI"

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        f"--output-filename={filename}",
        "--output-dir=build",
        "--include-package=config",
        "--include-package=trading",
        "--include-package=agents",
        "--include-package=llm",
        "--include-package=ui",
        "app_server.py",
    ]
    
    print(f"Building {filename} on {system}...")
    subprocess.run(cmd, check=True)
    print(f"Build complete: build/{filename}")

if __name__ == "__main__":
    build()
