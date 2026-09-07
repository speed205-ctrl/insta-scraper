"""
Configuration module using Pydantic Settings for type-safe environment configuration.
"""

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base project directory (root of Scrapper)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Instagram Credentials / Session Cookie ---
    instagram_username: str = Field(default="", description="Instagram login username")
    instagram_password: str = Field(default="", description="Instagram login password")
    instagram_session_id: str = Field(default="", description="Instagram sessionid cookie (bypasses checkpoints)")
    instagram_cookies: str = Field(default="", description="Full raw cookie header string from browser (bypasses 100% of blocks)")

    # --- Pipeline Settings ---
    outlier_multiplier: float = Field(
        default=3.0,
        gt=1.0,
        description="Multiplier over historical median views to consider a Reel as viral/outlier",
    )
    max_posts_per_account: int = Field(
        default=50,
        gt=0,
        description="Number of recent posts to scrape per target account",
    )
    request_delay_seconds: float = Field(
        default=3.0,
        ge=0.5,
        description="Delay in seconds between Instagram requests to prevent rate limiting",
    )

    # --- Whisper (STT) Settings ---
    whisper_model: str = Field(
        default="large-v3",
        description="Model size for faster-whisper (tiny, base, small, medium, large-v1, large-v2, large-v3)",
    )
    whisper_device: str = Field(
        default="cuda",
        description="Device to run Whisper on: 'cuda' or 'cpu'",
    )
    whisper_compute_type: str = Field(
        default="float16",
        description="Compute precision: 'float16', 'int8', 'float32'",
    )

    # --- LLM Provider Selection ('gemini' or 'ollama') ---
    llm_provider: str = Field(
        default="gemini",
        description="LLM provider to use for cognitive analysis: 'gemini' or 'ollama'",
    )

    # --- Gemini API Settings ---
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model identifier (e.g. gemini-2.5-flash)",
    )

    # --- Ollama Local LLM Settings ---
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
    )
    ollama_model: str = Field(
        default="llama3.1:8b",
        description="Ollama local model name (e.g. llama3.1:8b, gemma2:9b, mistral:7b)",
    )

    # --- Telegram Notifications ---
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token for alert notifications",
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID to send notifications to",
    )

    # --- Database & Storage Paths ---
    db_path: str = Field(
        default="data/scrapper.db",
        description="Path to SQLite database file relative to project root",
    )
    audio_dir: str = Field(
        default="data/audio",
        description="Directory to save downloaded audio files relative to project root",
    )

    @property
    def absolute_db_path(self) -> Path:
        """Returns the absolute path to the SQLite database file."""
        return PROJECT_ROOT / self.db_path

    @property
    def absolute_audio_dir(self) -> Path:
        """Returns the absolute path to the audio cache directory."""
        return PROJECT_ROOT / self.audio_dir

    def ensure_directories(self) -> None:
        """Ensure necessary data and audio directories exist."""
        self.absolute_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.absolute_audio_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
