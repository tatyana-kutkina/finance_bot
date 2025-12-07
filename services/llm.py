from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, OpenAIError
from pydantic import SecretStr
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.config import settings

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_secret(secret: Optional[SecretStr]) -> Optional[str]:
    """Безопасно извлекаем секретное значение."""
    return secret.get_secret_value() if secret else None


def _resolve_provider() -> tuple[str, str, Optional[str]]:
    """Определяем провайдера, ключ и base_url."""
    provider = (settings.AI_PROVIDER or "openai").lower()
    if provider == "deepseek":
        api_key = _get_secret(settings.DEEPSEEK_API_KEY)
    else:
        provider = "openai"
        api_key = _get_secret(settings.OPENAI_API_KEY)
        base_url = settings.OPENAI_BASE_URL

    if not api_key:
        raise ValueError("AI provider API key is not configured")

    return provider, api_key, base_url if provider == "openai" else None


_provider, _api_key, _base_url = _resolve_provider()
_openai_client: Optional[AsyncOpenAI] = None


def _get_openai_client() -> AsyncOpenAI:
    """Ленивая инициализация AsyncOpenAI для OpenAI-совместимых API."""
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=_api_key, base_url=_base_url)
    return _openai_client


def _to_lc_messages(messages: List[Dict[str, str]]):
    """Конвертируем сообщения в формат LangChain."""
    if not ChatOpenAI or not SystemMessage or not HumanMessage or not AIMessage:
        raise ImportError("langchain-openai и langchain-core нужны для langchain_deepseek провайдера")

    role_map = {
        "system": SystemMessage,
        "user": HumanMessage,
        "assistant": AIMessage,
    }
    try:
        return [role_map[msg["role"]](msg["content"]) for msg in messages]
    except KeyError as exc:
        raise ValueError("Некорректный формат сообщений для LLM") from exc


async def generate_chat_response(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Делает вызов LLM и возвращает только текст ответа.

    messages: список словарей с ключами role/content, совместимыми с OpenAI API.
    """
    model_name = model or settings.AI_MODEL

    if _provider == "deepseek":
        lc_messages = _to_lc_messages(messages)
        deepseek = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
        )
        try:
            response = await deepseek.ainvoke(lc_messages)
        except Exception as exc:
            logger.exception("Ошибка вызова langchain_deepseek: %s", exc)
            raise
        content = getattr(response, "content", None)
    else:
        try:
            response = await _get_openai_client().chat.completions.create(
                model=model_name,
                messages=messages,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except OpenAIError as exc:
            logger.exception("Ошибка вызова OpenAI: %s", exc)
            raise
        content = response.choices[0].message.content if response.choices else None

    if not content:
        raise ValueError("AI провайдер вернул пустой ответ")

    return content.strip()
