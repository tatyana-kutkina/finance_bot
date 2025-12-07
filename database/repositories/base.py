from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Shared helpers for repositories."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, instance):
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance):
        await self.session.delete(instance)
        await self.session.flush()

    async def commit(self):
        await self.session.commit()

    async def refresh(self, instance):
        await self.session.refresh(instance)
        return instance


