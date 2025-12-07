from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select

from database.models import Transaction
from database.repositories.base import BaseRepository


class TransactionRepository(BaseRepository):
    async def get_by_id(self, transaction_id: int) -> Optional[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> List[Transaction]:
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        if start_date:
            stmt = stmt.where(Transaction.date >= start_date)
        if end_date:
            stmt = stmt.where(Transaction.date <= end_date)
        stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        amount: Decimal | float | int,
        category: str,
        raw_text: str | None = None,
        spend_date: date | None = None,
    ) -> Transaction:
        decimal_amount = Decimal(str(amount))
        transaction = Transaction(
            user_id=user_id,
            amount=decimal_amount,
            category=category,
            raw_text=raw_text,
            date=spend_date or date.today(),
        )
        await self.add(transaction)
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction

    async def delete_by_id(self, transaction_id: int) -> bool:
        transaction = await self.get_by_id(transaction_id)
        if not transaction:
            return False
        await self.session.delete(transaction)
        await self.session.commit()
        return True


