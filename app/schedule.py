"""When each day's puzzle exists and when it can be played.

Players get the puzzle for their own local date, so a date is live somewhere on Earth from
00:00 in UTC+14 (the first zone to reach it) until 24:00 in UTC-12 (the last to leave it):
from 10:00 UTC the day before until 12:00 UTC the day after.

- A date can be played once it has started somewhere: `latest_open_date`.
- Its puzzle is generated and stored an hour before that, at 09:00 UTC the day before, by
  `keep_ahead`, a background task that also catches up after any downtime.
"""

import asyncio
import datetime as dt
import logging

from . import store
from .puzzle import LAUNCH

FIRST_ZONE = dt.timedelta(hours=14)  # UTC+14 (Line Islands) starts every date first
LAST_ZONE = dt.timedelta(hours=12)  # UTC-12 (Baker Island) ends every date last
LEAD = dt.timedelta(hours=1)  # how early a puzzle is generated before its date starts
CHECK_EVERY = dt.timedelta(minutes=5)

log = logging.getLogger("uvicorn.error")


def latest_open_date(now: dt.datetime) -> dt.date:
    """The newest date that has already started in some timezone."""
    return (now + FIRST_ZONE).date()


def due_dates(now: dt.datetime) -> list[dt.date]:
    """Dates that must be stored by `now`: every date that is today anywhere, plus the next
    one once it's less than LEAD away from starting."""
    first, last = (now - LAST_ZONE).date(), (now + FIRST_ZONE + LEAD).date()
    return [first + dt.timedelta(days=k) for k in range((last - first).days + 1) if first + dt.timedelta(days=k) >= LAUNCH]


def ensure(now: dt.datetime) -> None:
    for date in due_dates(now):
        if store.store_if_missing(date.isoformat()):
            log.info("Generated the puzzle for %s", date)


def _seconds_until_next_check(now: dt.datetime) -> float:
    """Wake at the next moment a new date becomes due (09:00 UTC), or sooner for routine checks."""
    due_at = dt.datetime.combine(now.date(), dt.time(), dt.UTC) + dt.timedelta(days=1) - FIRST_ZONE - LEAD
    while due_at <= now:
        due_at += dt.timedelta(days=1)
    return min((due_at - now).total_seconds(), CHECK_EVERY.total_seconds()) + 0.5


async def keep_ahead() -> None:
    """Runs for the life of the server."""
    while True:
        now = dt.datetime.now(dt.UTC)
        try:
            await asyncio.to_thread(ensure, now)
        except Exception:
            log.exception("Generating upcoming puzzles failed; retrying on the next check")
        await asyncio.sleep(_seconds_until_next_check(dt.datetime.now(dt.UTC)))
