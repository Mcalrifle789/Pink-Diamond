"""SQLite access layer for Pink Diamond. Initializes from database/schema.sql."""

import os
import sqlite3
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "database"

# Serverless hosts (Vercel) mount the deployment read-only, so the db file has
# to be relocatable. Locally this still resolves to database/pink-diamond.db.
DB_PATH = Path(os.environ.get("PD_DB_PATH") or _DATA_DIR / "pink-diamond.db")
SCHEMA_PATH = Path(os.environ.get("PD_SCHEMA_PATH") or _DATA_DIR / "schema.sql")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(query, params).fetchone()


def run(query: str, params: tuple = ()) -> int:
    with connect() as conn:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid
