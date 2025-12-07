from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Transaction
from database.repositories.transaction import TransactionRepository

logger = logging.getLogger(__name__)


@dataclass
class TransactionInput:
    """Входные данные для создания транзакции."""

    user_id: int
    amount: Decimal | float | int
    category: str
    raw_text: Optional[str] = None
    spend_date: Optional[date] = None


@dataclass
class WeeklyCategoryStat:
    """DTO для статистики по категориям за неделю."""

    category: str
    total: Decimal


class FinanceService:
    """Сервис бизнес-логики финансовых операций."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.transaction_repo = TransactionRepository(session)

    @staticmethod
    def _normalize_amount(amount: Decimal | float | int) -> Decimal:
        try:
            decimal_amount = Decimal(str(amount))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("Некорректное значение суммы") from exc

        if decimal_amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        return decimal_amount.quantize(Decimal("0.01"))

    @staticmethod
    def _normalize_category(category: str) -> str:
        if not category or not category.strip():
            raise ValueError("Категория не может быть пустой")
        return category.strip()

    @staticmethod
    def _normalize_date(spend_date: Optional[date]) -> date:
        return spend_date or date.today()

    async def add_transaction(self, data: TransactionInput) -> Transaction:
        if data.user_id <= 0:
            raise ValueError("user_id должен быть положительным")

        amount = self._normalize_amount(data.amount)
        category = self._normalize_category(data.category)
        spend_date = self._normalize_date(data.spend_date)

        # AICODE-NOTE: Валюта не хранится — предполагаем единую (RUB) для MVP.
        transaction = await self.transaction_repo.create(
            user_id=data.user_id,
            amount=amount,
            category=category,
            raw_text=data.raw_text,
            spend_date=spend_date,
        )
        return transaction

    async def get_week_stats(
        self, user_id: int, base_date: Optional[date] = None
    ) -> List[WeeklyCategoryStat]:
        """
        Возвращает статистику по категориям за последние 7 дней (включая base_date).
        """
        if user_id <= 0:
            raise ValueError("user_id должен быть положительным")

        end_date = base_date or date.today()
        start_date = end_date - timedelta(days=6)

        stmt = (
            select(
                Transaction.category,
                func.sum(Transaction.amount).label("total_amount"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
        )

        result = await self.session.execute(stmt)
        rows = result.all()
        return [
            WeeklyCategoryStat(category=row.category, total=row.total_amount)
            for row in rows
        ]


# AICODE-TODO: Добавить методы для произвольных диапазонов и лимитов/бюджетов.
