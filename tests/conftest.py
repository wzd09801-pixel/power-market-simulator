from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import get_db_session, get_engine, get_session_factory
from backend.app.main import create_app
from backend.app.models import forecasting as _forecasting  # noqa: F401
from backend.app.models import intelligence as _intelligence  # noqa: F401
from backend.app.models import knowledge as _knowledge  # noqa: F401
from backend.app.models import market as _market  # noqa: F401
from backend.app.models import operations as _operations  # noqa: F401
from backend.app.models import recommendation as _recommendation  # noqa: F401
from backend.app.models import scenario as _scenario  # noqa: F401
from backend.app.models import weather as _weather  # noqa: F401


@pytest.fixture
def db_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
