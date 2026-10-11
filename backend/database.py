"""Database access for Pink Diamond.

Two backends behind one small API (one / all / run / insert / transaction):

- Postgres when DATABASE_URL is set — required for real payments, because the
  ledger of what customers paid for must survive restarts.
- SQLite otherwise (local development; /tmp on Vercel, which is wiped on every
  cold start and therefore never allowed to take money — see payments.live()).

Queries are written with SQLite's `?` placeholders and translated for Postgres.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "database"

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or ""
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

# Serverless hosts (Vercel) mount the deployment read-only, so the SQLite file
# has to be relocatable. Locally this resolves to database/pink-diamond.db.
DB_PATH = Path(os.environ.get("PD_DB_PATH") or _DATA_DIR / "pink-diamond.db")
SCHEMA_PATH = Path(os.environ.get("PD_SCHEMA_PATH") or _DATA_DIR / "schema.sql")
PG_SCHEMA_PATH = _DATA_DIR / "schema.postgres.sql"


def persistent() -> bool:
    """True when stored data survives a restart of the serving process."""
    if IS_POSTGRES:
        return True
    return not str(DB_PATH).replace("\\", "/").startswith("/tmp/")


def _pg_sql(query: str) -> str:
    return query.replace("%", "%%").replace("?", "%s")


class _Conn:
    """Uniform cursor-ish wrapper so callers never branch on the backend."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, query: str, params: tuple = ()):
        if IS_POSTGRES:
            return self.raw.execute(_pg_sql(query), params)
        return self.raw.execute(query, params)


@contextmanager
def transaction():
    """One atomic unit of work. Rows read inside it are locked on Postgres
    when the query uses FOR UPDATE (stripped on SQLite, which locks the file)."""
    if IS_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as raw:
            with raw.transaction():
                yield _Conn(raw)
    else:
        raw = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        try:
            raw.execute("BEGIN IMMEDIATE")
            yield _SqliteConn(raw)
            raw.execute("COMMIT")
        except BaseException:
            raw.execute("ROLLBACK")
            raise
        finally:
            raw.close()


class _SqliteConn(_Conn):
    def execute(self, query: str, params: tuple = ()):
        return self.raw.execute(query.replace(" FOR UPDATE", ""), params)


def lock(conn: _Conn, name: str) -> None:
    """Hold a named lock until the transaction ends (SQLite's BEGIN IMMEDIATE
    already serializes writers)."""
    if IS_POSTGRES:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (name,))


def init_db() -> None:
    if IS_POSTGRES:
        import psycopg

        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            conn.execute(PG_SCHEMA_PATH.read_text(encoding="utf-8"))
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def one(query: str, params: tuple = ()):
    with transaction() as conn:
        return conn.execute(query, params).fetchone()


def all(query: str, params: tuple = ()) -> list:  # noqa: A001 - mirrors one()/run()
    with transaction() as conn:
        return conn.execute(query, params).fetchall()


def run(query: str, params: tuple = ()) -> int:
    """Execute a statement; returns the number of affected rows."""
    with transaction() as conn:
        return conn.execute(query, params).rowcount


def insert(query: str, params: tuple = ()) -> int:
    """INSERT one row into a table with an integer `id`; returns that id."""
    with transaction() as conn:
        if IS_POSTGRES:
            return conn.execute(query + " RETURNING id", params).fetchone()["id"]
        return conn.execute(query, params).lastrowid
