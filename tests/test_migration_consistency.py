from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from backend.app.db.base import Base
from backend.app.db.migration_consistency import (
    MigrationConsistencyError,
    check_migration_consistency,
)
from backend.app.models import forecasting as _forecasting  # noqa: F401
from backend.app.models import intelligence as _intelligence  # noqa: F401
from backend.app.models import knowledge as _knowledge  # noqa: F401
from backend.app.models import market as _market  # noqa: F401
from backend.app.models import operations as _operations  # noqa: F401
from backend.app.models import recommendation as _recommendation  # noqa: F401
from backend.app.models import scenario as _scenario  # noqa: F401
from backend.app.models import weather as _weather  # noqa: F401


def test_migration_consistency_allows_fresh_empty_database() -> None:
    engine = create_engine("sqlite+pysqlite://")

    check_migration_consistency(engine)


def test_migration_consistency_rejects_stamped_database_with_missing_tables() -> None:
    engine = create_engine("sqlite+pysqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260602_0010')")
        )

    with pytest.raises(MigrationConsistencyError, match="missing expected tables"):
        check_migration_consistency(engine)


def test_migration_consistency_accepts_complete_head_schema() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260615_0017')")
        )

    check_migration_consistency(engine)


def test_migration_consistency_rejects_head_schema_missing_lease_token() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE workflow_runs DROP COLUMN lease_token"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260615_0017')")
        )

    with pytest.raises(MigrationConsistencyError, match="lease_token"):
        check_migration_consistency(engine)


def test_migration_consistency_rejects_head_schema_missing_decision_table() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE recommendation_decisions"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260615_0017')")
        )

    with pytest.raises(MigrationConsistencyError, match="recommendation_decisions"):
        check_migration_consistency(engine)


def test_migration_consistency_rejects_head_schema_missing_document_review_table() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE knowledge_document_reviews"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260610_0016')")
        )

    with pytest.raises(MigrationConsistencyError, match="knowledge_document_reviews"):
        check_migration_consistency(engine)


def test_migration_consistency_rejects_head_schema_missing_hydro_optimization_table() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE hydro_optimization_runs"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260615_0017')")
        )

    with pytest.raises(MigrationConsistencyError, match="hydro_optimization_runs"):
        check_migration_consistency(engine)
