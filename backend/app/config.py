"""
Central configuration. Everything is read from environment variables
(via a .env file in local dev) so no secrets are ever hardcoded.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    DATABASE_URL: str = "sqlite:///./ats_system.db"

    SERPAPI_API_KEY: str = ""
    GOOGLE_CSE_API_KEY: str = ""
    GOOGLE_CSE_ID: str = ""

    COMPANY_PROFILE_MAX_AGE_DAYS: int = 30


settings = Settings()
