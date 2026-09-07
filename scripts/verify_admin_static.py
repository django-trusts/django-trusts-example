#!/usr/bin/env python
"""Start gunicorn and confirm WhiteNoise serves collected admin CSS."""

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATIC_FILE = REPO / "static" / "admin" / "css" / "base.css"
PORT = os.environ.get("PORT", "8765")

if not STATIC_FILE.is_file():
    raise SystemExit(f"missing collected file: {STATIC_FILE}")

env = os.environ.copy()
env.setdefault("DJANGO_SETTINGS_MODULE", "example.settings")
# Leave DATABASE_URL unset so this check stays on SQLite.

proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "gunicorn",
        "example.wsgi",
        "--bind",
        f"127.0.0.1:{PORT}",
        "--access-logfile",
        "-",
        "--log-file",
        "-",
    ],
    cwd=REPO,
    env=env,
)
url = f"http://127.0.0.1:{PORT}/static/admin/css/base.css"
try:
    body = None
    last_err = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status != 200:
                    raise SystemExit(f"{url} returned {response.status}")
                body = response.read()
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last_err = err
            time.sleep(0.2)
    else:
        raise SystemExit(f"could not fetch {url}: {last_err}")
    if b"body" not in body.lower() and b"html" not in body.lower():
        if len(body) < 100:
            raise SystemExit(f"{url} body too small ({len(body)} bytes)")
    print(f"admin-static-ok {url} bytes={len(body)}")
finally:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
