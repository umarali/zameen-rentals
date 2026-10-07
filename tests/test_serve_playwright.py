"""tests/serve_playwright.py must remove its temporary data directory on SIGTERM."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parent / "serve_playwright.py"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port, proc, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert proc.poll() is None, "server exited early"
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise AssertionError("server never listened")


def test_sigterm_removes_temporary_data_directory(tmp_path):
    port = _free_port()
    env = {**os.environ, "TMPDIR": str(tmp_path), "PLAYWRIGHT_PORT": str(port)}
    env.pop("ZAMEENRENTALS_DB_DIR", None)
    proc = subprocess.Popen([sys.executable, str(SERVER)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_port(port, proc)
        assert list(tmp_path.glob("zameen-playwright-*")), "data dir not created"
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert list(tmp_path.glob("zameen-playwright-*")) == []
