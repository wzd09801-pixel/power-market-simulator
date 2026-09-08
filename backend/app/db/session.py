from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


@lru_cache
def get_engine(database_url: str) -> Engine:
    connect_args = {"connect_timeout": 1} if database_url.startswith("postgresql") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


@lru_cache
def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), autoflush=False, expire_on_commit=False)


def get_db_session() -> Iterator[Session]:
    factory = get_session_factory(get_settings().database_url)
    with factory() as session:
        yield session


def check_database_connectivity(database_url: str) -> bool:
    try:
        engine = get_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
