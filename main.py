import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from core.config import settings
from core.logger import setup_logging
from database.repositories.user import UserRepository
from database.session import get_session
from services.ai_service import AIService
from services.finance_service import FinanceService, TransactionInput


logger = logging.getLogger(__name__)
bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
dp = Dispatcher()
ai_service = AIService()


async def ensure_user(session, telegram_id: int):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(telegram_id)
    if user:
        return user
    return await repo.create(telegram_id=telegram_id)


async def process_user_text(
    message: Message, user_text: str, raw_text: str | None = None
):
    try:
        parsed = await ai_service.parse_transaction_text(user_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось распарсить сообщение: %s", exc)
        await message.answer(
            "Не получилось понять трату. "
            "Попробуйте переформулировать."
        )
        return

    async with get_session() as session:
        try:
            user = await ensure_user(session, message.from_user.id)
            finance_service = FinanceService(session)
            await finance_service.add_transaction(
                TransactionInput(
                    user_id=user.id,
                    amount=parsed.amount,
                    category=parsed.category,
                    raw_text=raw_text or user_text,
                    spend_date=parsed.date,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка при сохранении транзакции: %s", exc)
            await message.answer("Не получилось сохранить трату, попробуйте позже.")
            return

    await message.answer(
        f"✅ Записано: {parsed.category} — {parsed.amount} RUB "
        f"({parsed.date})"
    )


@dp.message(CommandStart())
async def handle_start(message: Message):
    async with get_session() as session:
        await ensure_user(session, message.from_user.id)

    await message.answer(
        "Привет! Пришли мне текст или голосовую заметку о трате, "
        "я сохраню её и помогу вести учёт. Команда /stats покажет расходы за неделю."
    )


@dp.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message):
    await process_user_text(message, message.text or "", raw_text=message.text)


@dp.message(F.voice)
async def handle_voice(message: Message):
    if not message.voice:
        return

    bot_instance = message.bot
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as tmp_file:
            tmp_path = Path(tmp_file.name)
        # AICODE-NOTE: Whisper читает с диска, поэтому сохраняем voice
        # во временный файл.
        telegram_file = await bot_instance.get_file(message.voice.file_id)
        await bot_instance.download(telegram_file, destination=tmp_path)

        transcript = await ai_service.transcribe_audio(str(tmp_path))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка при обработке голосового сообщения: %s", exc)
        await message.answer(
            "Не получилось обработать голосовое сообщение, попробуйте ещё раз."
        )
        return
    finally:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Не удалось удалить временный файл %s", tmp_path)

    await process_user_text(message, transcript, raw_text=transcript)


@dp.message(Command("stats", "week"))
async def handle_stats(message: Message):
    async with get_session() as session:
        user = await ensure_user(session, message.from_user.id)
        finance_service = FinanceService(session)
        stats = await finance_service.get_week_stats(user.id)

    if not stats:
        await message.answer("За последние 7 дней трат пока нет.")
        return

    lines = [f"• {item.category}: {item.total} RUB" for item in stats]
    await message.answer("Статистика за 7 дней:\n" + "\n".join(lines))


async def main():
    setup_logging()
    # AICODE-NOTE: Простое polling-приложение для MVP без дополнительных middlewares.
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
