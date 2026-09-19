import datetime as dt
import json
from contextlib import asynccontextmanager
from pathlib import Path

from markupsafe import Markup, escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import i18n, store
from .puzzle import LAUNCH, LIVES
from .store import puzzle_for

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.check_writable()  # refuse to start if the puzzle database can't be written
    yield


app = FastAPI(title="Nono", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
# A string as a JS literal inside a double-quoted HTML attribute, e.g. :aria-label="on ? {{ t.mute|js }} : ...".
templates.env.filters["js"] = lambda value: Markup(escape(json.dumps(value)))


def render(request: Request, name: str, context: dict):
    lang = i18n.pick(request)
    context = {"lang": lang, "langs": i18n.LANGS, "t": i18n.STRINGS[lang], **context}
    response = templates.TemplateResponse(request, name, context)
    response.headers["Vary"] = "Cookie, Accept-Language"
    return response


def puzzle_date(value: str) -> dt.date:
    """Parse a YYYY-MM-DD day, 404ing on anything that has no puzzle."""
    try:
        date = dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(404, "Not a day") from None
    if value != date.isoformat():  # fromisoformat also takes "20260917"; keep one URL per day
        raise HTTPException(404, "Not a day")
    # The client picks "today" in its own timezone; allow one day ahead for zones east of UTC.
    if not LAUNCH <= date <= dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1):
        raise HTTPException(404, "No puzzle for that day")
    return date


def page(request: Request):
    # The client reads the day from the URL path and loads /board itself.
    return render(request, "index.html", {"launch": LAUNCH.isoformat()})


@app.get("/")
def index(request: Request):
    return page(request)


@app.get("/calendar")
def calendar(request: Request):
    return page(request)


# These live at the root: a service worker only controls pages at or below its own path.
@app.get("/sw.js")
def service_worker():
    return FileResponse(BASE / "static/sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(BASE / "static/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(BASE / "static/favicon.ico")


@app.get("/board")
def board(request: Request, date: str):
    date = puzzle_date(date)
    p = puzzle_for(date.isoformat())
    cfg = {
        "date": date.isoformat(),
        "number": (date - LAUNCH).days + 1,
        "label": i18n.STRINGS[i18n.pick(request)][p.difficulty],
        "size": p.size,
        "solution": p.solution,
        "fp": p.fingerprint,
        "rows": p.rows,
        "cols": p.cols,
        "maxLives": LIVES[p.size],
    }
    # How many numbers the longest row / column clue has, so CSS can size the cells to fit.
    clue_lens = {"row_clue_len": max(len(r) for r in p.rows), "col_clue_len": max(len(c) for c in p.cols)}
    return render(request, "board.html", {"p": p, "cfg": cfg, **clue_lens})


# Declared last so it doesn't shadow /board.
@app.get("/{day}")
def day_page(request: Request, day: str):
    puzzle_date(day)
    return page(request)


assert {"easy", "medium", "hard"} <= i18n.STRINGS[i18n.DEFAULT].keys(), "every difficulty needs a label"
