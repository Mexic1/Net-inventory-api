"""Test fixtures.

Tests run against a real PostgreSQL, not SQLite: the app relies on Postgres
behaviour (unique-violation IntegrityError, String(45) binding), and CI uses a
postgres:17 service container. A SQLite stand-in would pass while hiding
dialect bugs.

DATABASE_URL is set before importing app.db, because that module builds the
engine at import time.
"""

import os

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5432/test"
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    # Drop first: the suite asserts on exact inventory contents, so it must not
    # inherit rows left behind by a previous run, a dev session or a container
    # pointed at the same database.
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session(engine):
    """A session inside a transaction that is rolled back after each test.

    Nesting the session in an outer transaction keeps tests isolated without
    recreating the schema between them, and without truncating tables.
    """
    connection = engine.connect()
    transaction = connection.begin()
    with Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as s:
        yield s
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def device_payload():
    return {
        "hostname": "edge-01",
        "mgmt_ip": "10.0.0.1",
        "vendor": "cisco",
        "model": "ISR4331",
        "site": "hq",
        "role": "router",
    }
