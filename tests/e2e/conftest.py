"""E2E fixtures: hermetic static server on demo data + optional full stack."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="session")
def static_server_url() -> str:
    """WebUI serving data/demo with demo export artifacts."""
    export_dir = ROOT / "export-demo"
    env = os.environ.copy()
    env["CATALOG_DATA_DIR"] = str(ROOT / "data" / "demo")
    env["CATALOG_EXPORT_DIR"] = str(export_dir)
    if not (export_dir / "API台帳_帳票.html").exists():
        subprocess.run(
            [sys.executable, "scripts/export_markdown.py"],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
    port = _free_port()
    env["CATALOG_PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, "web/server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    else:
        output = process.stdout.read() if process.stdout else ""
        process.terminate()
        raise RuntimeError(f"static server failed to start:\n{output}")
    yield url
    process.terminate()
    process.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    """Self-managed chromium (explicit sandbox flags for CI/containers)."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        yield browser
        browser.close()


@pytest.fixture()
def app_page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()
