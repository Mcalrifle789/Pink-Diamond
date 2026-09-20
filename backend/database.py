"""SQLite access layer for Pink Diamond. Initializes from database/schema.sql."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "pink-diamond.db"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "database" / "schema.sql"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
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
