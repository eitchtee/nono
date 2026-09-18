import datetime as dt
import json
from pathlib import Path

from markupsafe import Markup, escape

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import i18n
from .puzzle import DIFFICULTIES, daily

BASE = Path(__file__).parent
MAX_LIVES = 3
LAUNCH = dt.date(2026, 9, 1)  # puzzle #1; the calendar starts here

app = FastAPI(title="Nono")
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
    p = daily(date.isoformat())
    cfg = {
        "date": date.isoformat(),
        "number": (date - LAUNCH).days + 1,
        "label": i18n.STRINGS[i18n.pick(request)][p.difficulty],
        "size": p.size,
        "solution": p.solution,
        "rows": p.rows,
        "cols": p.cols,
        "maxLives": MAX_LIVES,
    }
    return render(request, "board.html", {"p": p, "cfg": cfg, "row_clue_len": max(len(r) for r in p.rows)})


# Declared last so it doesn't shadow /board.
@app.get("/{day}")
def day_page(request: Request, day: str):
    puzzle_date(day)
    return page(request)


assert set(DIFFICULTIES) <= i18n.STRINGS[i18n.DEFAULT].keys(), "every difficulty needs a label"
