"""Engine, session factory and declarative base.

`create_engine` does not open a connection, so importing this module is safe
before PostgreSQL is reachable. The first real connection happens in the app's
lifespan handler, which is what makes compose's healthcheck-gated startup and
CI's service container behave the same way.
"""

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env, or see the README quick start."
        )
    return url


engine: Engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with SessionLocal() as session:
        yield session
