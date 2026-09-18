import pytest

from app import store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets an empty puzzle database instead of the real ./data/nono.db."""
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "nono.db")
    store.puzzle_for.cache_clear()
    yield
    store.puzzle_for.cache_clear()
