from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.reflection import Inspector

from backend.app.core.config import get_settings
from backend.app.db.session import get_engine

logger = logging.getLogger(__name__)

REVISION_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("20260529_0001", ("audit_events", "recommendation_runs")),
    ("20260530_0002", ("feature_snapshots", "recommendation_reviews")),
    (
        "20260530_0003",
        ("weather_locations", "weather_raw_payloads", "weather_ingestion_runs", "weather_records"),
    ),
    ("20260530_0004", ("weather_quality_issues", "weather_feature_snapshots")),
    ("20260530_0005", ("weather_feature_reviews",)),
    (
        "20260530_0006",
        (
            "market_data_sources",
            "market_source_endpoints",
            "market_raw_artifacts",
            "market_ingestion_runs",
            "market_ingestion_run_items",
            "market_quality_issues",
            "market_endpoint_health_checks",
        ),
    ),
    ("20260531_0007", ("market_artifact_reviews", "market_parsing_runs", "market_observations")),
    ("20260531_0008", ()),
    (
        "20260602_0009",
        (
            "forecast_research_datasets",
            "forecast_research_dataset_import_runs",
            "forecast_research_price_points",
            "forecast_research_quality_issues",
            "forecast_research_model_runs",
            "forecast_research_predictions",
        ),
    ),
    ("20260602_0010", ("raw_objects", "workflow_runs", "workday_calendar_overrides")),
    (
        "20260602_0011",
        (
            "knowledge_documents",
            "knowledge_document_versions",
            "knowledge_chunks",
            "knowledge_authorization_audits",
        ),
    ),
    (
        "20260602_0012",
        ("intelligence_briefs", "intelligence_brief_reviews", "intelligence_question_runs"),
    ),
    ("20260602_0013", ()),
    ("20260603_0014", ()),
    ("20260609_0015", ("recommendation_decisions", "recommendation_decision_feedback")),
    ("20260610_0016", ("knowledge_document_reviews",)),
    ("20260615_0017", ("hydro_optimization_runs",)),
)

REVISION_COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "20260602_0013": {
        "workflow_runs": (
            "available_at",
            "claimed_at",
            "lease_expires_at",
            "worker_id",
            "attempt_count",
        ),
        "weather_locations": (
            "collection_enabled",
            "verification_status",
            "source_url",
            "notes",
        ),
    },
    "20260603_0014": {
        "workflow_runs": (
            "scheduled_for",
            "schedule_identity",
            "lease_token",
        ),
    },
}


class MigrationConsistencyError(RuntimeError):
    pass


def check_migration_consistency(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables:
        application_tables = tables & _known_application_tables()
        if application_tables:
            raise MigrationConsistencyError(
                "Database has application tables but no Alembic revision marker: "
                + ", ".join(sorted(application_tables))
                + "."
            )
        return

    with engine.connect() as connection:
        revisions = tuple(connection.scalars(text("SELECT version_num FROM alembic_version")))
    if len(revisions) != 1:
        raise MigrationConsistencyError("Expected exactly one Alembic revision marker.")
    revision = revisions[0]
    revision_names = [item[0] for item in REVISION_TABLES]
    if revision not in revision_names:
        raise MigrationConsistencyError(
            f"Database Alembic revision '{revision}' is not recognized."
        )

    expected_tables: set[str] = set()
    for current_revision, required_tables in REVISION_TABLES:
        expected_tables.update(required_tables)
        if current_revision == revision:
            break
    missing_tables = expected_tables - tables
    if missing_tables:
        raise MigrationConsistencyError(
            f"Database revision '{revision}' is missing expected tables: "
            + ", ".join(sorted(missing_tables))
            + "."
        )

    for current_revision, table_columns in REVISION_COLUMNS.items():
        if revision_names.index(revision) < revision_names.index(current_revision):
            continue
        _check_columns(inspector, table_columns)


def _check_columns(inspector: Inspector, table_columns: dict[str, tuple[str, ...]]) -> None:
    for table_name, expected_columns in table_columns.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = set(expected_columns) - actual_columns
        if missing_columns:
            raise MigrationConsistencyError(
                f"Database table '{table_name}' is missing expected columns: "
                + ", ".join(sorted(missing_columns))
                + "."
            )


def _known_application_tables() -> set[str]:
    return {table for _revision, tables in REVISION_TABLES for table in tables}


def _repair_message(error: Exception) -> str:
    return (
        f"Migration consistency check failed: {error}\n"
        "The database was not modified. Back up the PostgreSQL volume before repair. "
        "Inspect the Alembic revision and schema manually, then either repair the existing "
        "volume or start a separate fresh database. Do not delete or reset historical volumes "
        "as an automated recovery step."
    )


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    logging.basicConfig(level=logging.INFO)
    try:
        check_migration_consistency(get_engine(get_settings().database_url))
    except MigrationConsistencyError as exc:
        logger.error(_repair_message(exc))
        return 1
    logger.info("Migration consistency check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
