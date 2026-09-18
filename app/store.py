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


@lru_cache(maxsize=128)
def puzzle_for(date: str) -> Puzzle:
    """The day's puzzle: the stored one if it exists, otherwise generated and stored now."""
    with _connect() as conn:
        row = conn.execute("SELECT difficulty, size, solution FROM puzzles WHERE date = ?", (date,)).fetchone()
        if row is None:
            p = daily(date)
            # OR IGNORE: if another worker stored this day first, keep theirs and read it back below.
            conn.execute(
                "INSERT OR IGNORE INTO puzzles (date, difficulty, size, solution) VALUES (?, ?, ?, ?)",
                (date, p.difficulty, p.size, p.solution),
            )
            row = conn.execute("SELECT difficulty, size, solution FROM puzzles WHERE date = ?", (date,)).fetchone()
    return Puzzle.from_solution(*row)
