import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings
from core.logger import setup_logging
from database.repositories.user import UserRepository
from database.session import get_session
from services.ai_service import AIService
from services.finance_service import FinanceService, TransactionInput


logger = logging.getLogger(__name__)
bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
dp = Dispatcher(storage=MemoryStorage())
ai_service = AIService()

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статистика за 7 дней")],
        [KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="➕ Добавить категорию")],
        [KeyboardButton(text="📂 Мои категории")],
    ],
    resize_keyboard=True,
)
WELCOME_TEXT = (
    "Привет! Пришли мне текст или голосовую заметку о трате, "
    "я сохраню её и помогу вести учёт. Кнопка «Статистика за 7 дней» "
    "покажет последние расходы."
)


class AddCategoryState(StatesGroup):
    waiting_for_name = State()
    waiting_for_match_text = State()


async def ensure_user(session, telegram_id: int):
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(telegram_id)
    if user:
        return user
    return await repo.create(telegram_id=telegram_id)


async def send_stats(message: Message):
    async with get_session() as session:
        user = await ensure_user(session, message.from_user.id)
        finance_service = FinanceService(session)
        stats = await finance_service.get_week_stats(user.id)

    if not stats:
        await message.answer("За последние 7 дней трат пока нет.", reply_markup=main_menu)
        return

    lines = [f"• {item.category}: {item.total} RUB" for item in stats]
    await message.answer(
        "Статистика за 7 дней:\n" + "\n".join(lines), reply_markup=main_menu
    )


async def process_user_text(
    message: Message, user_text: str, raw_text: str | None = None
):
    raw_message = raw_text or user_text
    async with get_session() as session:
        try:
            user = await ensure_user(session, message.from_user.id)
            finance_service = FinanceService(session)
            user_categories = await finance_service.list_categories(user.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка при подготовке данных пользователя: %s", exc)
            await message.answer("Не получилось обработать запрос, попробуйте позже.")
            return

        try:
            parsed = await ai_service.parse_transaction_text(
                user_text,
                preferred_categories=[category.name for category in user_categories],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Не удалось распарсить сообщение: %s", exc)
            await message.answer(
                "Не получилось понять трату. "
                "Попробуйте переформулировать."
            )
            return

        try:
            await finance_service.add_transaction(
                TransactionInput(
                    user_id=user.id,
                    amount=parsed.amount,
                    category=parsed.category,
                    raw_text=raw_message,
                    spend_date=parsed.date,
                ),
                user_categories=user_categories,
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

    await message.answer(WELCOME_TEXT, reply_markup=main_menu)


@dp.message(Command("help"))
async def handle_help(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu)


async def _start_add_category_dialog(message: Message, state: FSMContext):
    await message.answer(
        "Введите короткое название категории (например, «Кофе вне офиса»)."
    )
    await state.set_state(AddCategoryState.waiting_for_name)


@dp.message(Command("add_category"))
async def handle_add_category_start(message: Message, state: FSMContext):
    await _start_add_category_dialog(message, state)


@dp.message(F.text == "➕ Добавить категорию")
async def handle_add_category_button(message: Message, state: FSMContext):
    await _start_add_category_dialog(message, state)


@dp.message(F.text == "📂 Мои категории")
async def handle_list_categories(message: Message):
    async with get_session() as session:
        user = await ensure_user(session, message.from_user.id)
        finance_service = FinanceService(session)
        categories = await finance_service.list_categories(user.id)

    if not categories:
        await message.answer(
            "Категорий пока нет. Нажмите «➕ Добавить категорию», чтобы создать первую.",
            reply_markup=main_menu,
        )
        return

    lines = [f"• {item.name} — триггер «{item.match_text}»" for item in categories]
    await message.answer(
        "Ваши категории:\n" + "\n".join(lines),
        reply_markup=main_menu,
    )


@dp.message(AddCategoryState.waiting_for_name)
async def handle_add_category_name(message: Message, state: FSMContext):
    category_name = (message.text or "").strip()
    if not category_name:
        await message.answer("Название не может быть пустым, попробуйте снова.")
        return

    await state.update_data(category_name=category_name)
    await message.answer(
        "Теперь отправьте фразу-триггер. Если она встретится в сообщении, "
        "мы применим эту категорию."
    )
    await state.set_state(AddCategoryState.waiting_for_match_text)


@dp.message(AddCategoryState.waiting_for_match_text)
async def handle_add_category_match_text(message: Message, state: FSMContext):
    match_text = (message.text or "").strip()
    if not match_text:
        await message.answer("Фраза не может быть пустой, введите её ещё раз.")
        return

    data = await state.get_data()
    category_name = data.get("category_name")

    async with get_session() as session:
        try:
            user = await ensure_user(session, message.from_user.id)
            finance_service = FinanceService(session)
            category = await finance_service.create_category(
                user_id=user.id,
                name=category_name,
                match_text=match_text,
            )
        except ValueError as exc:  # noqa: BLE001
            await message.answer(f"Не получилось сохранить: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка при создании категории: %s", exc)
            await message.answer("Не удалось сохранить категорию, попробуйте позже.")
            return

    await state.clear()
    await message.answer(
        f"Категория «{category.name}» создана. Сообщения с фразой "
        f"«{category.match_text}» будут относиться к ней.",
        reply_markup=main_menu,
    )


@dp.message(F.text == "📊 Статистика за 7 дней")
async def handle_menu_stats(message: Message):
    await send_stats(message)


@dp.message(F.text == "ℹ️ Помощь")
async def handle_menu_help(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu)


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
    await send_stats(message)


async def main():
    setup_logging()
    # AICODE-NOTE: Простое polling-приложение для MVP без дополнительных middlewares.
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
