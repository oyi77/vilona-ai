from __future__ import annotations
import subprocess
import sys
import time
import os


def test_paper_headless_boot_does_not_exit():
    """Process must survive 3+ seconds with default paper/headless config."""
    # Empty env → all defaults: paper_trading=True, headless=True, no tokens
    # load_dotenv() reads .env if present, so explicitly clear token vars to
    # force the "no credentials" path and guarantee a paper-mode boot.
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
           "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
           "TEMP": os.environ.get("TEMP", ""), "TMP": os.environ.get("TMP", ""),
           "vilona_TELEGRAM_BOT_TOKEN": "", "vilona_RELAY_URL": "",
           "vilona_RELAY_DEVICE_TOKEN": ""}
    proc = subprocess.Popen(
        [sys.executable, "app_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
    )
    start = time.monotonic()
    try:
        # Wait 3s before sending SIGTERM
        time.sleep(3.0)
        # Must still be alive
        rc = proc.poll()
        elapsed = time.monotonic() - start
        assert rc is None, (
            f"Process exited prematurely after {elapsed:.1f}s with code {rc}"
        )
        # Send SIGTERM — should trigger clean shutdown within ~5s
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
