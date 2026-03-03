import os

from app.core.settings import get_settings


def test_database_url_normalization_postgres_scheme_to_asyncpg():
    os.environ["DATABASE_URL"] = "postgres://user:pass@localhost:5432/dbname"
    get_settings.cache_clear()
    s = get_settings()
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert "user:pass@localhost:5432/dbname" in s.database_url


def test_database_url_normalization_postgresql_scheme_to_asyncpg():
    os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/dbname"
    get_settings.cache_clear()
    s = get_settings()
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_database_url_keeps_asyncpg_scheme():
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
    get_settings.cache_clear()
    s = get_settings()
    assert s.database_url == "postgresql+asyncpg://user:pass@localhost:5432/dbname"
