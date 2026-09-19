"""Keeps every day's puzzle exactly as it was first generated.

The generator is deterministic, but changing it (new sizes, a different solver, a
tweaked density) would silently turn old days into different puzzles, breaking
saved games and shared links. So the first request for a day stores its grid in
SQLite and every later request reads it back.
"""

import os
import sqlite3
from functools import lru_cache
from pathlib import Path

from .puzzle import Puzzle, daily

# Docker sets NONO_DB to a path on a volume; locally it lives in ./data (gitignored).
DB_PATH = Path(os.environ.get("NONO_DB", Path(__file__).parent.parent / "data" / "nono.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    date       TEXT PRIMARY KEY,  -- YYYY-MM-DD
    difficulty TEXT NOT NULL,
    size       INTEGER NOT NULL,
    solution   TEXT NOT NULL,     -- size*size "0"/"1" characters, row by row
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(SCHEMA)
    return conn


def check_writable() -> None:
    """Called at startup: fail right away with the fix in the message, rather than start
    healthy and then return a 500 for every day that isn't stored yet."""
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")  # takes the write lock, so it needs write access
            conn.rollback()
    except (OSError, sqlite3.OperationalError) as e:
        uid = os.getuid() if hasattr(os, "getuid") else "?"
        raise RuntimeError(
            f"Can't write the puzzle database at {DB_PATH} ({e}). Its directory must be writable by "
            f"the user running the app (uid {uid}). With a bind mount, run on the host: "
            f"sudo chown -R {uid}:{uid} <the mounted directory>"
        ) from None


def store_if_missing(date: str) -> bool:
    """Generate and store the day's puzzle unless it's already stored. True if it was generated."""
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM puzzles WHERE date = ?", (date,)).fetchone():
            return False
        p = daily(date)
        # OR IGNORE: if another worker stored this day first, theirs is kept.
        cur = conn.execute(
            "INSERT OR IGNORE INTO puzzles (date, difficulty, size, solution) VALUES (?, ?, ?, ?)",
            (date, p.difficulty, p.size, p.solution),
        )
        return cur.rowcount == 1


@lru_cache(maxsize=128)
def puzzle_for(date: str) -> Puzzle:
    """The day's puzzle, as stored. Upcoming days are stored ahead of time by the scheduler;
    older days nobody has opened yet are generated and stored on their first request."""
    store_if_missing(date)
    with _connect() as conn:
        row = conn.execute("SELECT difficulty, size, solution FROM puzzles WHERE date = ?", (date,)).fetchone()
    return Puzzle.from_solution(*row)
