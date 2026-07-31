from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行配置；环境变量优先于 .env 文件。"""

    app_name: str = "AI Social Relationship Assistant"
    database_url: str = "sqlite:///../data/social_agent.db"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    ocr_lang: str = "ch"
    screenshot_dir: str = "../data/screenshots"
    keep_screenshots: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def screenshot_path(self) -> Path:
        return Path(self.screenshot_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()

