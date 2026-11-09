import subprocess
import sys
from pathlib import Path

BASE_CMD = [
    sys.executable, "-m", "nuitka",
    "--standalone",
    "--onefile",
    "--output-dir=build",
    "--include-package=config",
    "--include-package=trading",
    "--include-package=agents",
    "--include-package=llm",
    "--include-package=ui",
    "--enable-plugin=pyqt6",
    "app_server.py",
]


def build_windows():
    """Build Windows .exe using Nuitka"""
    Path("build").mkdir(exist_ok=True)
    cmd = BASE_CMD + ["--output-filename=Vilona-AI.exe"]
    subprocess.run(cmd, check=True)


def build_linux():
    """Build Linux binary using Nuitka"""
    Path("build").mkdir(exist_ok=True)
    cmd = BASE_CMD + ["--output-filename=Vilona-AI"]
    subprocess.run(cmd, check=True)


def build_macos():
    """Build macOS .app using Nuitka"""
    Path("build").mkdir(exist_ok=True)
    cmd = BASE_CMD + ["--macos-create-app-bundle", "--output-filename=Vilona-AI"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "windows"
    builders = {
        "windows": build_windows,
        "linux": build_linux,
        "macos": build_macos,
    }
    if target not in builders:
        print(f"Unknown target {target!r}; expected one of {list(builders)}", file=sys.stderr)
        sys.exit(1)
    builders[target]()
