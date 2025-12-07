from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from database.models import User
from database.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(self, telegram_id: int, settings: dict | None = None) -> User:
        user = User(telegram_id=telegram_id, settings=settings)
        await self.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user


