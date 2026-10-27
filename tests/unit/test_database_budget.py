import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db import session as database


def test_database_budget_is_validated_and_applied_to_connections(monkeypatch):
    settings = Settings(_env_file=None, database_statement_timeout_ms=10000)
    captured = {}

    def create(url, **options):
        captured.update(options)
        return object()

    monkeypatch.setattr(database, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "create_engine", create)
    database.engine.cache_clear()
    try:
        database.engine()
        assert captured["connect_args"] == {
            "connect_timeout": 3,
            "options": "-c statement_timeout=10000",
        }
    finally:
        database.engine.cache_clear()
    for value in [0, 30001, "10000; DROP TABLE chunks"]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, database_statement_timeout_ms=value)
