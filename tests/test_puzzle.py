import datetime as dt
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app import schedule, store
from app.i18n import from_accept_language
from app.main import app
from app.puzzle import LAUNCH, TIERS, Puzzle, clues, daily, given_away, line_solvable, solve_passes

# The first 120 days, as ISO dates.
DAYS = [(LAUNCH + dt.timedelta(days=k)).isoformat() for k in range(120)]


def test_clues():
    assert clues([0, 1, 1, 0, 1]) == [2, 1]
    assert clues([0, 0, 0]) == [0]


def test_daily_is_deterministic_and_solvable():
    p = daily("2026-09-18")
    assert p == daily.__wrapped__("2026-09-18")
    assert (p.size, p.difficulty) in TIERS
    assert line_solvable(p.grid)
    assert p != daily("2026-09-19")


def test_difficulty_varies_by_day():
    mix = Counter((daily(d).size, daily(d).difficulty) for d in DAYS)
    assert set(mix) == set(TIERS)  # every size/tier combination shows up, and nothing else


def test_days_measure_inside_their_tier():
    for d in DAYS[:60]:
        p = daily(d)
        assert TIERS[(p.size, p.difficulty)].fits(given_away(p.grid), solve_passes(p.grid)), p


def test_lives_depend_on_size():
    client = TestClient(app)
    lives = {}
    for size in (5, 10):
        day = next(d for d in DAYS if daily(d).size == size)
        text = client.get("/board", params={"date": day}).text
        lives[size] = int(text.split('"maxLives": ')[1].split(",")[0].split("}")[0])
    assert lives == {5: 3, 10: 5}


def test_line_solver_rejects_ambiguous_grid():
    # Diagonal 2x2 has two solutions with the same clues.
    assert not line_solvable(((1, 0), (0, 1)))


def test_board_endpoint():
    client = TestClient(app)
    res = client.get("/board", params={"date": "2026-09-18"})
    assert res.status_code == 200
    assert '"number": 18' in res.text
    for bad in ["2099-01-01", "2026-08-31", "nope"]:
        assert client.get("/board", params={"date": bad}).status_code == 404


def test_day_urls():
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/2026-09-17").status_code == 200
    assert client.get("/calendar").status_code == 200
    for bad in ["/2026-08-31", "/2099-01-01", "/2026-13-01", "/20260917", "/nope"]:
        assert client.get(bad).status_code == 404


def test_pwa_files():
    client = TestClient(app)
    manifest = client.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    for icon in manifest.json()["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert client.get("/sw.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/favicon.ico").status_code == 200


def test_accept_language():
    assert from_accept_language("pt-BR,pt;q=0.9,en;q=0.8") == "pt-BR"
    assert from_accept_language("pt-PT") == "pt-BR"
    assert from_accept_language("en-GB,en;q=0.9") == "en"
    assert from_accept_language("fr-FR,fr;q=0.9,pt;q=0.8,en;q=0.5") == "pt-BR"  # best supported by q
    assert from_accept_language("de;q=0.9,en;q=0.3,pt;q=0.1") == "en"
    assert from_accept_language("fr") == from_accept_language("") == "en"


def test_language_choice():
    client = TestClient(app)
    pt = client.get("/", headers={"Accept-Language": "pt-BR"})
    assert '<html lang="pt-BR">' in pt.text and "Como jogar" in pt.text
    assert "Cookie" in pt.headers["vary"]
    board = client.get("/board", params={"date": "2026-09-03"}, headers={"Accept-Language": "pt-BR"})
    assert "Pintar" in board.text and "Fácil" in board.text
    # A picked language (cookie) beats the browser's
    client.cookies.set("nono_lang", "en")
    assert "How to play" in client.get("/", headers={"Accept-Language": "pt-BR"}).text
    client.cookies.set("nono_lang", "xx")  # unknown values fall back to detection
    assert "Como jogar" in client.get("/", headers={"Accept-Language": "pt-BR"}).text


def test_first_generation_is_stored_and_kept(monkeypatch):
    first = store.puzzle_for("2026-09-18")
    assert first == daily("2026-09-18")

    # Simulate a future generator change: a stored day must not change.
    monkeypatch.setattr(store, "daily", lambda date: Puzzle.from_grid("easy", ((1, 0), (0, 1))))
    store.puzzle_for.cache_clear()
    assert store.puzzle_for("2026-09-18") == first
    # ...while a day that was never requested uses the new generator.
    assert store.puzzle_for("2026-09-17").size == 2


def test_solution_round_trip():
    p = daily("2026-09-18")
    assert Puzzle.from_solution(p.difficulty, p.size, p.solution) == p


def test_unwritable_database_fails_at_startup(monkeypatch, tmp_path):
    # A path whose parent is a file can never be created, like an unwritable mount.
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setattr(store, "DB_PATH", blocker / "nono.db")
    with pytest.raises(RuntimeError, match="Can't write the puzzle database"):
        with TestClient(app):
            pass


def test_board_sends_the_puzzle_fingerprint():
    p = daily("2026-09-03")
    assert len(p.fingerprint) == 16
    assert p.fingerprint != daily("2026-09-04").fingerprint
    text = TestClient(app).get("/board", params={"date": "2026-09-03"}).text
    assert f'"fp": "{p.fingerprint}"' in text


def test_dates_open_when_they_start_anywhere():
    # 2026-09-20 starts first in UTC+14, at 10:00 UTC on the 19th.
    assert schedule.latest_open_date(dt.datetime(2026, 9, 19, 9, 59, tzinfo=dt.UTC)) == dt.date(2026, 9, 19)
    assert schedule.latest_open_date(dt.datetime(2026, 9, 19, 10, 0, tzinfo=dt.UTC)) == dt.date(2026, 9, 20)


def test_puzzles_are_generated_an_hour_before_they_open():
    at = lambda h, m: dt.datetime(2026, 9, 19, h, m, tzinfo=dt.UTC)
    assert dt.date(2026, 9, 20) not in schedule.due_dates(at(8, 59))
    assert dt.date(2026, 9, 20) in schedule.due_dates(at(9, 0))  # 1 hour before it opens
    # Every date that is still today somewhere (down to UTC-12) stays covered.
    assert schedule.due_dates(at(9, 0)) == [dt.date(2026, 9, 18), dt.date(2026, 9, 19), dt.date(2026, 9, 20)]
    # The task wakes exactly at 09:00 UTC rather than up to a check interval late.
    assert schedule._seconds_until_next_check(at(8, 58)) == 120.5


def test_scheduler_stores_upcoming_days():
    schedule.ensure(dt.datetime(2026, 9, 19, 9, 0, tzinfo=dt.UTC))
    assert not store.store_if_missing("2026-09-20")  # already there
    assert store.store_if_missing("2026-09-10")  # never requested, so generated now


def test_days_lists_every_open_day_with_its_puzzle():
    res = TestClient(app).get("/api/days")
    days = res.json()["days"]
    last = schedule.latest_open_date(dt.datetime.now(dt.UTC))
    assert min(days) == LAUNCH.isoformat() and max(days) == last.isoformat()
    assert len(days) == (last - LAUNCH).days + 1
    p = daily("2026-09-03")
    assert days["2026-09-03"] == {"fp": p.fingerprint, "solution": p.solution}
    assert res.headers["cache-control"] == "no-cache"


def test_static_files_are_versioned_so_deploys_reach_players():
    client = TestClient(app)
    page = client.get("/").text
    for name in ("app.js", "style.css"):
        url = page.split(f'/static/{name}?v=')[1].split('"')[0]
        versioned = client.get(f"/static/{name}?v={url}")
        assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/static/app.js").headers["cache-control"] == "no-cache"
