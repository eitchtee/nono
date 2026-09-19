"""Deterministic daily puzzle generation.

There is one puzzle per day. The date seeds everything, so everyone gets the same puzzle,
and every grid is checked by a pure line-by-line solver, which guarantees a unique solution
that never needs guessing.

Each day draws a size and a difficulty tier, then grids are generated until one measures
inside that tier: difficulty is measured, not assumed from the fill density. Changing these
rules changes every day that isn't stored yet; the store pins each day once generated.
"""

import datetime as dt
import hashlib
import random
from dataclasses import dataclass
from functools import lru_cache

LAUNCH = dt.date(2026, 9, 1)  # puzzle #1
LIVES = {5: 3, 10: 5}  # by board size


@dataclass(frozen=True)
class Tier:
    weight: int  # relative odds of a day getting this size and tier
    density: float  # chance of each square being filled; nudges candidates toward the tier
    # Share of the grid the clues give away before any row and column are combined...
    min_given: float = 0.0
    max_given: float = 1.0
    # ...and how many full passes the line solver needs.
    min_passes: int = 1
    max_passes: int = 99

    def fits(self, given: float, passes: int) -> bool:
        return self.min_given <= given <= self.max_given and self.min_passes <= passes <= self.max_passes


# Bands set from measured distributions: a 10x10 at 58% gives away 43% up front (median),
# 27-60% across most grids. 5x5 can't be made truly hard, so it only comes as easy or medium.
TIERS = {
    (5, "easy"): Tier(2, 0.62, min_given=0.68),
    (5, "medium"): Tier(2, 0.52, max_given=0.48),
    (10, "easy"): Tier(2, 0.60, min_given=0.50, max_passes=3),
    (10, "medium"): Tier(3, 0.56, min_given=0.32, max_given=0.45),
    (10, "hard"): Tier(3, 0.50, max_given=0.25, min_passes=4),
}

Line = list[int | None]  # 1 filled, 0 empty, None unknown


@dataclass(frozen=True)
class Puzzle:
    difficulty: str  # easy / medium / hard
    size: int
    grid: tuple[tuple[int, ...], ...]
    rows: list[list[int]]
    cols: list[list[int]]

    @property
    def solution(self) -> str:
        return "".join(str(v) for row in self.grid for v in row)

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.solution)

    @classmethod
    def from_grid(cls, difficulty: str, grid) -> "Puzzle":
        return cls(difficulty, len(grid), grid, [clues(r) for r in grid], [clues(c) for c in zip(*grid)])

    @classmethod
    def from_solution(cls, difficulty: str, size: int, solution: str) -> "Puzzle":
        """Inverse of .solution, used when loading a stored puzzle."""
        cells = [int(ch) for ch in solution]
        return cls.from_grid(difficulty, tuple(tuple(cells[r * size : (r + 1) * size]) for r in range(size)))


def fingerprint(solution: str) -> str:
    """Short hash of a grid. Saved games carry it, so a day whose puzzle ever changes
    (generator change, lost database) is detected and its stale save discarded."""
    return hashlib.sha256(solution.encode()).hexdigest()[:16]


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


def solve_passes(grid) -> int | None:
    """Full row-then-column passes the line solver needs to finish the grid, or None if it
    gets stuck (the puzzle would need guessing)."""
    h, w = len(grid), len(grid[0])
    rows = [clues(r) for r in grid]
    cols = [clues(c) for c in zip(*grid)]
    known: list[Line] = [[None] * w for _ in range(h)]
    solved = passes = 0
    while True:
        before = solved
        passes += 1
        for r in range(h):
            known[r] = _deduce(rows[r], known[r])
        for c in range(w):
            col = _deduce(cols[c], [known[r][c] for r in range(h)])
            for r in range(h):
                known[r][c] = col[r]
        solved = sum(v is not None for row in known for v in row)
        if solved == h * w:
            return passes
        if solved == before:
            return None


def line_solvable(grid) -> bool:
    return solve_passes(grid) is not None


def given_away(grid) -> float:
    """Share of the grid decidable from single rows or columns on an empty board."""
    n = len(grid)
    blank = [None] * n
    known = {(r, i) for r, row in enumerate(grid) for i, v in enumerate(_deduce(clues(row), blank)) if v is not None}
    known |= {(i, c) for c, col in enumerate(zip(*grid)) for i, v in enumerate(_deduce(clues(col), blank)) if v is not None}
    return len(known) / (n * n)


def _random_grid(rng: random.Random, size: int, density: float):
    return tuple(tuple(int(rng.random() < density) for _ in range(size)) for _ in range(size))


@lru_cache(maxsize=128)
def daily(date: str) -> Puzzle:
    rng = random.Random(hashlib.sha256(f"nono:{date}".encode()).digest())
    (size, difficulty), tier = rng.choices(list(TIERS.items()), weights=[t.weight for t in TIERS.values()])[0]
    while True:
        grid = _random_grid(rng, size, tier.density)
        passes = solve_passes(grid)
        if passes is not None and tier.fits(given_away(grid), passes):
            return Puzzle.from_grid(difficulty, grid)
