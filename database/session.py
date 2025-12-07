from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings


def get_database_path() -> Path:
    """
    Resolve the database path. If DB_NAME is relative, place DB file in project root.
    """
    db_path = Path(settings.DB_NAME)
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parent.parent / db_path
    return db_path


def get_database_url() -> str:
    db_path = get_database_path()
    return f"sqlite+aiosqlite:///{db_path}"


# AICODE-NOTE: Resolve DB path relative to project root for local dev convenience.
engine: AsyncEngine = create_async_engine(get_database_url(), echo=False, future=True)
async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session."""
    async with async_session_factory() as session:
        yield session


