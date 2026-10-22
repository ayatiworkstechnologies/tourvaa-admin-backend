import pytest
from sqlalchemy import create_engine, text

from app import main


def test_startup_rejects_database_behind_alembic_head(monkeypatch):
    stale_engine = create_engine("sqlite://")
    try:
        with stale_engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('stale_revision')"))

        monkeypatch.setattr(main, "engine", stale_engine)

        with pytest.raises(RuntimeError, match=r"Database migration mismatch:.*stale_revision.*upgrade head"):
            main.validate_database_migration_head()
    finally:
        stale_engine.dispose()


def test_startup_accepts_database_at_application_head(monkeypatch):
    monkeypatch.setattr(
        main,
        "database_migration_heads",
        lambda: (frozenset({"head_revision"}), frozenset({"head_revision"})),
    )

    main.validate_database_migration_head()
