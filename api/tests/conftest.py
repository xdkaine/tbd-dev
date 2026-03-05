"""Shared test fixtures for the TBD Platform API test suite.

Uses an in-process SQLite async engine so tests don't need PostgreSQL.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

# In-memory aiosqlite engine (no PostgreSQL needed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture()
async def db_engine():
    """Create a fresh in-memory database engine for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session bound to the test engine."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Application / HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def app(db_engine):
    """Return a FastAPI app wired to the test database.

    Overrides the `get_db` dependency so all routes use the test engine.
    """
    from app.database import get_db
    from app.main import app as _app

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    _app.dependency_overrides[get_db] = _override_get_db
    yield _app
    _app.dependency_overrides.clear()


@pytest.fixture()
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client that talks directly to the test app (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_token():
    """Factory fixture that creates a valid JWT for a given user."""

    def _make(
        user_id: uuid.UUID | None = None,
        username: str = "testuser",
        role: str = "JAS_Developer",
    ) -> str:
        from app.middleware.auth import create_access_token

        uid = user_id or uuid.uuid4()
        token, _ = create_access_token(uid, username, role)
        return token

    return _make


@pytest.fixture()
def auth_headers(make_token):
    """Return Authorization headers for a default developer user."""

    def _headers(
        user_id: uuid.UUID | None = None,
        username: str = "testuser",
        role: str = "JAS_Developer",
    ) -> dict[str, str]:
        token = make_token(user_id=user_id, username=username, role=role)
        return {"Authorization": f"Bearer {token}"}

    return _headers


# ---------------------------------------------------------------------------
# User factory
# ---------------------------------------------------------------------------


@pytest.fixture()
async def create_user(db_session):
    """Factory fixture that inserts a User row and returns it."""

    async def _create(
        username: str = "testuser",
        display_name: str = "Test User",
        email: str = "test@sdc.cpp",
        ad_dn: str = "CN=testuser,OU=Users,DC=sdc,DC=cpp",
    ):
        from app.models.user import User

        user = User(
            username=username,
            display_name=display_name,
            email=email,
            ad_dn=ad_dn,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _create
