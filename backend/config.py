"""
Application configuration via environment variables.
All settings are loaded from .env file or environment.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings - loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "BackVora"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = ""

    # JWT Auth
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7
    allow_registration: bool = False

    # Database
    database_url: str = "sqlite:///./data/linkbuilder.db"

    # Ahrefs API
    ahrefs_api_key: str = ""
    ahrefs_mcp_url: str = "https://api.ahrefs.com/mcp/mcp"

    # Email (Resend)
    resend_api_key: str = ""
    email_from_name: str = "BackVora"
    email_from_address: str = ""  # Must be verified domain in Resend

    # Email (IMAP/SMTP for inbox)
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    email_account: str = ""
    email_password: str = ""

    # Payment
    paypal_address: str = ""  # PayPal address for publisher invoices

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # BackVora operational agent
    agent_model: str = "opus"
    agent_max_results: int = 20
    agent_claude_cli_path: str = "/home/slither/.local/bin/claude"
    agent_claude_cli_timeout_seconds: int = 60
    agent_claude_cli_cwd: str = "/tmp"

    # OpenAI (DALL-E 3)
    openai_api_key: str = ""

    # CamHours API
    camhours_api_key: str = ""

    # Image APIs
    pexels_api_key: str = ""
    fal_api_key: str = ""

    # Slack
    slack_webhook_url: str = ""

    # Search
    brave_api_key: str = ""

    # Rate Limiting
    scrape_delay_seconds: float = 2.0
    ahrefs_requests_per_minute: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
