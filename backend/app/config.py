from pathlib import Path
import re

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_transcribe_model: str = "whisper-1"
    openai_summary_model: str = "gpt-4o-mini"
    demo_mode: bool = False
    max_upload_mb: int = 25
    database_url: str = "sqlite:///./meetings.db"
    upload_dir: str = "uploads"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def use_demo(self) -> bool:
        return self.demo_mode or not self.openai_api_key.strip()

    @property
    def has_api_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def key_hint(self) -> str | None:
        key = self.openai_api_key.strip()
        if not key:
            return None
        if len(key) <= 8:
            return "••••"
        return f"{key[:5]}…{key[-4:]}"


settings = Settings()


def _upsert_env_value(name: str, value: str) -> None:
    path = BACKEND_DIR / ".env"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"^{re.escape(name)}=.*$", re.MULTILINE)
    line = f"{name}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        prefix = f"{text.rstrip()}\n" if text.strip() else ""
        text = f"{prefix}{line}\n"
    path.write_text(text, encoding="utf-8")


def apply_openai_key(api_key: str) -> None:
    """Update the running process and persist the key to backend/.env."""
    cleaned = api_key.strip()
    settings.openai_api_key = cleaned
    if cleaned:
        settings.demo_mode = False
        _upsert_env_value("DEMO_MODE", "false")
    _upsert_env_value("OPENAI_API_KEY", cleaned)
