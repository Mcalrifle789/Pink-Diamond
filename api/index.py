"""Vercel entrypoint.

The static site (index.html, styles.css, app.js ...) is served straight from the
repo root. Everything under /api is rewritten here, where the FastAPI service in
backend/ is mounted as an ASGI app.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Serverless filesystems are read-only apart from /tmp, so the SQLite file has
# to live there. It is ephemeral per instance — swap PD_DB_PATH for a managed
# Postgres URL before this handles real accounts.
os.environ.setdefault("PD_DB_PATH", "/tmp/pink-diamond.db")

import database as db  # noqa: E402
from main import app  # noqa: E402,F401

if not Path(os.environ["PD_DB_PATH"]).exists():
    db.init_db()
