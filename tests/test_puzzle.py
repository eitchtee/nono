from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.i18n import from_accept_language
from app.main import app
from app import store
from app.puzzle import DIFFICULTIES, Puzzle, clues, daily, line_solvable


def test_clues():
    assert clues([0, 1, 1, 0, 1]) == [2, 1]
    assert clues([0, 0, 0]) == [0]


def test_daily_is_deterministic_and_solvable():
    p = daily("2026-09-18")
    assert p == daily.__wrapped__("2026-09-18")
    assert p.size == DIFFICULTIES[p.difficulty][0]
    assert line_solvable(p.grid)
    assert p != daily("2026-09-19")


def test_difficulty_varies_by_day():
    before = Counter(daily(f"2026-09-{d:02d}").difficulty for d in range(1, 19))
    assert set(before) == {"easy", "medium", "hard"}
    after = Counter(daily(f"2026-10-{d:02d}").difficulty for d in range(1, 32))
    assert set(after) == {"easy", "medium"}  # 15x15 isn't picked from 2026-09-19 on


def test_rule_changes_keep_older_days():
    # Pinned before 15x15 was dropped; these days must never change.
    assert (daily("2026-09-18").difficulty, daily("2026-09-18").solution[:15]) == ("hard", "111010111010000")
    assert (daily("2026-09-03").difficulty, daily("2026-09-03").solution) == ("easy", "1001011000000001010011011")


def test_lives_depend_on_size():
    client = TestClient(app)
    lives = {}
    for day in ["2026-09-03", "2026-09-01", "2026-09-18"]:  # easy, medium, hard
        text = client.get("/board", params={"date": day}).text
        lives[daily(day).difficulty] = int(text.split('"maxLives": ')[1].split(",")[0].split("}")[0])
    assert lives == {"easy": 3, "medium": 5, "hard": 5}


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
