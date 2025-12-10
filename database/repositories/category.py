from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select

from database.models import Category
from database.repositories.base import BaseRepository


class CategoryRepository(BaseRepository):
    async def list_by_user(self, user_id: int) -> List[Category]:
        stmt = (
            select(Category)
            .where(Category.user_id == user_id)
            .order_by(Category.created_at.asc(), Category.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name_ci(self, user_id: int, name: str) -> Optional[Category]:
        stmt = select(Category).where(
            Category.user_id == user_id,
            func.lower(Category.name) == func.lower(name),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_match_text_ci(
        self, user_id: int, match_text: str
    ) -> Optional[Category]:
        stmt = select(Category).where(
            Category.user_id == user_id,
            func.lower(Category.match_text) == func.lower(match_text),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, user_id: int, name: str, match_text: str
    ) -> Category:
        category = Category(
            user_id=user_id,
            name=name,
            match_text=match_text,
        )
        await self.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def find_match_for_text(
        self, user_id: int, text: str
    ) -> Optional[Category]:
        normalized_text = text.lower()
        categories = await self.list_by_user(user_id)
        for category in categories:
            if category.match_text.lower() in normalized_text:
                # AICODE-NOTE: Простая подстрочная проверка для MVP; может давать
                # ложные срабатывания на общие слова.
                return category
        return None

