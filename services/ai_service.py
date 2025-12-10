from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date as dt_date, datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, SecretStr, ValidationError
from langchain_core.output_parsers import PydanticOutputParser
from openai import AsyncOpenAI, OpenAIError
from phoenix.otel import register
from opentelemetry.trace import Status, StatusCode


from core.config import settings
from services.llm import generate_chat_response
from services.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

tracer_provider = register(
    project_name="FinanceBot_Project",
    endpoint="http://localhost:6006/v1/traces",
    auto_instrument=True
)


@dataclass
class TransactionDTO:
    amount: float
    category: str
    date: dt_date
    raw_text: Optional[str] = None


class TransactionStructured(BaseModel):
    amount: float = Field(
        description="Сумма траты числом, без валюты, строго > 0",
    )
    category: str = Field(..., min_length=1, description="Краткая категория, одно-два слова")
    date: dt_date = Field(..., description="Дата операции в формате YYYY-MM-DD")


class AIService:
    """Сервис для работы с LLM (парсинг текста) и Whisper (STT)."""

    def __init__(self):
        self.model = settings.AI_MODEL
        self.audio_client = self._create_audio_client()
        self.tracer = tracer_provider.get_tracer(__name__)
        # AICODE-NOTE: Передаем pydantic_object именованным аргументом
        # для совместимости с текущей версией langchain_core.
        self.output_parser = PydanticOutputParser(
            pydantic_object=TransactionStructured
        )

    @staticmethod
    def _get_secret(secret: Optional[SecretStr]) -> Optional[str]:
        # Ленивая загрузка секретов, чтобы не светить их в логах.
        return secret.get_secret_value() if secret else None

    def _create_audio_client(self) -> AsyncOpenAI:
        api_key = self._get_secret(settings.OPENAI_API_KEY)
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for Whisper STT")

        # AICODE-NOTE: Whisper используем через OpenAI даже если чат-провайдер DeepSeek.
        return AsyncOpenAI(api_key=api_key)

    @staticmethod
    def _parse_date(value: str | None) -> dt_date:
        if not value:
            return dt_date.today()

        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            logger.warning("Не удалось распарсить дату '%s', используем текущую", value)
            # AICODE-TODO: Добавить более умный парсинг дат (NLP) при необходимости.
            return dt_date.today()

    async def parse_transaction_text(self, user_text: str) -> TransactionDTO:
        """Парсит текстовое описание траты пользователя в DTO."""
        if not user_text or not user_text.strip():
            raise ValueError("Текст для парсинга пустой")

        prompt = SYSTEM_PROMPT.format(
            today_date=dt_date.today().isoformat(),
            transaction_schema=TransactionStructured.model_json_schema(),
        )
        with self.tracer.start_as_current_span("parse_transaction_text", openinference_span_kind="chain") as span:
            span.set_input(user_text)
            try:
                message = await generate_chat_response(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_text.strip()},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=300,
                )
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.exception("Ошибка при вызове AI провайдера: %s", exc)
                raise

            try:
                structured = self.output_parser.parse(message)
                span.set_status(Status(StatusCode.OK))
                span.set_output(structured)
            except (ValidationError, json.JSONDecodeError) as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.exception("Не удалось распарсить структурированный ответ: %s", message)
                raise ValueError("Некорректный структурированный ответ от AI провайдера") from exc

        dto = TransactionDTO(
            amount=structured.amount,
            category=structured.category.strip(),
            date=structured.date,
            raw_text=user_text,
        )
        return dto

    async def transcribe_audio(self, file_path: str) -> str:
        """Транскрибирует аудио-файл через Whisper."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл {file_path} не найден")
        with self.tracer.start_as_current_span("transcribe_audio", openinference_span_kind="chain") as span:
            try:
                with path.open("rb") as audio_file:
                    response = await self.audio_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ru",
                    )
                span.set_status(Status(StatusCode.OK))
                span.set_output(response)
            except OpenAIError as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.exception("Ошибка транскрибации Whisper: %s", exc)
                raise

        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Whisper вернул пустой текст")

        return text.strip()
