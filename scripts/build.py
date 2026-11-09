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
        "--enable-plugin=pyqt6",
        "app_server.py",
    ]