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

# Serverless filesystems are read-only apart from /tmp, so the fallback SQLite
# file lives there. It is ephemeral per instance, which is why payments stay
# switched off until DATABASE_URL points at Postgres.
os.environ.setdefault("PD_DB_PATH", "/tmp/pink-diamond.db")

import database as db  # noqa: E402
from main import app  # noqa: E402,F401

# Postgres (DATABASE_URL) is the persistent store payments require; its schema
# is CREATE IF NOT EXISTS, so applying it on each cold start is safe.
if db.IS_POSTGRES or not Path(os.environ["PD_DB_PATH"]).exists():
    db.init_db()
