"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # LLM
    llm_provider: str = "anthropic"  # anthropic | openai | gemini
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_prefix": "ARC_", "env_file": ".env.local"}


settings = Settings()
