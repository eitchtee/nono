"""Deterministic daily puzzle generation.

There is one puzzle per day. The date seeds both the difficulty and the grid, so
everyone gets the same puzzle. Grids are rejected until a pure line-by-line solver
can finish them, which guarantees a unique solution that never needs guessing.
"""

import hashlib
import random
from dataclasses import dataclass
from functools import lru_cache

# difficulty -> (size, fill density, lives)
DIFFICULTIES = {
    "easy": (5, 0.6, 3),
    "medium": (10, 0.58, 5),
    "hard": (15, 0.55, 5),  # no longer picked for new days, but kept so old 15x15 days still load
}

# Which difficulties a day can get, with their relative odds. Each rule applies from its date
# onwards, so days generated under older rules keep exactly the same puzzle (the store also
# pins every day once served, but days nobody has opened yet only have the generator).
# Order matters: rng.choices draws from the dict in this order.
RULES = [
    ("2026-09-01", {"easy": 3, "medium": 4, "hard": 3}),
    ("2026-09-19", {"easy": 3, "medium": 4}),  # 15x15 dropped: too small to tap on phones
]


def odds_for(date: str) -> dict[str, int]:
    return next(odds for start, odds in reversed(RULES) if date >= start)


Line = list[int | None]  # 1 filled, 0 empty, None unknown


@dataclass(frozen=True)
class Puzzle:
    difficulty: str
    size: int
    grid: tuple[tuple[int, ...], ...]
    rows: list[list[int]]
    cols: list[list[int]]

    @property
    def solution(self) -> str:
        return "".join(str(v) for row in self.grid for v in row)

    @classmethod
    def from_grid(cls, difficulty: str, grid) -> "Puzzle":
        return cls(difficulty, len(grid), grid, [clues(r) for r in grid], [clues(c) for c in zip(*grid)])

    @classmethod
    def from_solution(cls, difficulty: str, size: int, solution: str) -> "Puzzle":
        """Inverse of .solution, used when loading a stored puzzle."""
        cells = [int(ch) for ch in solution]
        return cls.from_grid(difficulty, tuple(tuple(cells[r * size : (r + 1) * size]) for r in range(size)))


def clues(line) -> list[int]:
    runs, n = [], 0
    for v in line:
        if v:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    return runs or [0]


def _options(clue: list[int], known: Line):
    """Yield every full line matching the clue and the already-known cells."""
    n = len(known)
    blocks = [b for b in clue if b]

    def rec(bi: int, pos: int):
        if bi == len(blocks):
            if all(k != 1 for k in known[pos:]):
                yield [0] * (n - pos)
            return
        b = blocks[bi]
        reserved = sum(blocks[bi + 1 :]) + len(blocks) - bi - 1
        for start in range(pos, n - reserved - b + 1):
            if any(k == 1 for k in known[pos:start]):
                break  # a known fill would be left uncovered
            end = start + b
            if any(k == 0 for k in known[start:end]):
                continue
            prefix = [0] * (start - pos) + [1] * b
            nxt = end
            if end < n:
                if known[end] == 1:
                    continue
                prefix.append(0)
                nxt += 1
            for rest in rec(bi + 1, nxt):
                yield prefix + rest

    return rec(0, 0)


def _deduce(clue: list[int], known: Line) -> Line:
    opts = list(_options(clue, known))
    return [opts[0][i] if all(o[i] == opts[0][i] for o in opts) else known[i] for i in range(len(known))]


def line_solvable(grid) -> bool:
    h, w = len(grid), len(grid[0])
    rows = [clues(r) for r in grid]
    cols = [clues(c) for c in zip(*grid)]
    known: list[Line] = [[None] * w for _ in range(h)]
    solved = 0
    while True:
        before = solved
        for r in range(h):
            known[r] = _deduce(rows[r], known[r])
        for c in range(w):
            col = _deduce(cols[c], [known[r][c] for r in range(h)])
            for r in range(h):
                known[r][c] = col[r]
        solved = sum(v is not None for row in known for v in row)
        if solved == h * w:
            return True
        if solved == before:
            return False


@lru_cache(maxsize=128)
def daily(date: str) -> Puzzle:
    rng = random.Random(hashlib.sha256(f"nono:{date}".encode()).digest())
    odds = odds_for(date)
    difficulty = rng.choices(list(odds), weights=list(odds.values()))[0]
    size, density, _ = DIFFICULTIES[difficulty]
    while True:
        grid = tuple(tuple(int(rng.random() < density) for _ in range(size)) for _ in range(size))
        if line_solvable(grid):
            return Puzzle.from_grid(difficulty, grid)
