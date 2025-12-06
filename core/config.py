from pydantic_settings import BaseSettings
from pydantic import SecretStr
from typing import Optional


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: SecretStr

    # AI Provider
    OPENAI_API_KEY: SecretStr
    OPENAI_BASE_URL: Optional[str] = None  # For DeepSeek or other compatible APIs
    AI_MODEL: str = "gpt-4o-mini"

    # Database
    DB_NAME: str = "finance_bot.sqlite"
    
    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

