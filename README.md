# Nono

A new nonogram every day, in the spirit of [Termo](https://term.ooo).

Fill the grid using the row and column clues. Every move is checked on the spot: a wrong one costs a life (3 on a 5×5, 5 on a 10×10) and reveals the real square. Everyone gets the same puzzle each day, and the calendar has every day you missed.

## Features

- **One daily puzzle** (#1 is 2026-09-01). The date seeds a size (5×5 or 10×10) and a difficulty (easy, medium, or hard on 10×10), and grids are generated until one actually measures at that difficulty: how much the clues give away before you combine rows and columns, and how many passes a line solver needs. Every grid is solvable line by line, so it never needs guessing. Changing the rules in `app/puzzle.py` changes every day that isn't stored in the database yet.
- **Past puzzles** in a calendar at `/calendar`, and every day has its own URL (`/2026-09-17`).
- **Timezone-aware.** Players get their own local date. Each puzzle is generated an hour before its date begins anywhere (09:00 UTC the day before, for UTC+14), and a date can't be opened until it has started somewhere.
- **No accounts.** Progress lives in the browser's `localStorage`, tagged with a fingerprint of its puzzle so a save that no longer matches is discarded. The server only keeps each day's puzzle in SQLite, so changes to the generator never alter a day that's already stored.
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

The container runs as a non-root user on a read-only filesystem, with all Linux capabilities dropped. Its only writable path is the `nono-data` volume, which holds the puzzle database: keep it across upgrades. If you mount a host directory there instead, make it writable by the app's user first (`sudo chown -R 10001:10001 <dir>`); otherwise the container refuses to start and says so in its logs. It serves plain HTTP on port 8000, so put it behind a reverse proxy for HTTPS (needed to install the PWA), and set `FORWARDED_ALLOW_IPS` in `compose.yaml` to the proxy's address.

Locally the database is `./data/nono.db`; set `NONO_DB` to put it elsewhere.

## Project layout

```
app/
  main.py       routes
  puzzle.py     daily puzzle generation and the line solver
  store.py      SQLite store that pins each day's puzzle once generated
  schedule.py   when dates open, and the task that generates them ahead of time
  i18n.py       UI strings and language detection
  templates/    page shell and board
  static/       game logic (app.js), styles, service worker, icons
tests/
```

To add a language, add its strings to `STRINGS` and an entry to `LANGS` in `app/i18n.py`.

When deploying a change to the static files, bump `CACHE` in `app/static/sw.js` so installed copies pick it up.
