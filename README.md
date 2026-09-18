# Nono

A new nonogram every day, in the spirit of [Termo](https://term.ooo).

Fill the grid using the row and column clues. Every move is checked on the spot: a wrong one costs one of your three lives and reveals the real square. Everyone gets the same puzzle each day, and finishing it unlocks the days you missed.

## Features

- **One daily puzzle** (#1 is 2026-09-01). The date seeds both the difficulty (5×5, 10×10 or 15×15) and the grid, and every grid is checked to be solvable line by line, so it never needs guessing.
- **Past puzzles** in a calendar at `/calendar`, and every day has its own URL (`/2026-09-17`).
- **No accounts.** Progress lives in the browser's `localStorage`. The server only keeps each day's puzzle in SQLite, stored the first time the day is served, so changes to the generator never alter a day someone already played.
- **Mouse, touch and pen.** Drag to paint a line; right-click marks an X.
- **English and Brazilian Portuguese**, picked from the browser's language until the player chooses one.
- **Installable PWA** that works offline for days you've already opened.
- **Sound effects** synthesized with [Cuelume](https://github.com/Danilaa1/cuelume).

Built with FastAPI, Jinja, HTMX and Alpine.js. No build step.

## Running locally

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run uvicorn app.main:app --reload --reload-dir app
```

Open http://localhost:8000. Add `?debug` to the URL for a button that resets today's game.

Run the tests with:

```sh
uv run pytest
```

## Docker

```sh
cp compose.example.yaml compose.yaml
docker compose up -d --build
```

The container runs as a non-root user on a read-only filesystem, with all Linux capabilities dropped. Its only writable path is the `nono-data` volume, which holds the puzzle database: keep it across upgrades. It serves plain HTTP on port 8000, so put it behind a reverse proxy for HTTPS (needed to install the PWA), and set `FORWARDED_ALLOW_IPS` in `compose.yaml` to the proxy's address.

Locally the database is `./data/nono.db`; set `NONO_DB` to put it elsewhere.

## Project layout

```
app/
  main.py       routes
  puzzle.py     daily puzzle generation and the line solver
  store.py      SQLite store that pins each day's puzzle once generated
  i18n.py       UI strings and language detection
  templates/    page shell and board
  static/       game logic (app.js), styles, service worker, icons
tests/
```

To add a language, add its strings to `STRINGS` and an entry to `LANGS` in `app/i18n.py`.

When deploying a change to the static files, bump `CACHE` in `app/static/sw.js` so installed copies pick it up.
