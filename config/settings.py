"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # LLM
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # Local runner
    watch_dir: str = "/tmp/arc_watch"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "ARC_", "env_file": ".env"}


settings = Settings()
