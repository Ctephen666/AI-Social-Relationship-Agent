from functools import lru_cache
from pathlib import Path
import os
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.runtime import data_directory


def environment_file_path() -> Path:
    override = os.getenv("SPARK_AGENT_ENV_FILE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        candidates = [executable.parent / ".env"]
        if len(executable.parents) > 2:
            candidates.append(executable.parents[2] / ".env")
    else:
        candidates = [Path(__file__).resolve().parents[2] / ".env"]
    return next((path for path in candidates if path.is_file()), candidates[0])


def _environment_file() -> str:
    """Backward-compatible string path used by pydantic-settings."""
    return str(environment_file_path())


class Settings(BaseSettings):
    """运行配置；环境变量优先于 .env 文件。"""

    app_name: str = "AI Social Relationship Assistant"
    database_url: str = Field(default_factory=lambda: f"sqlite:///{(data_directory() / 'social_agent.db').as_posix()}")
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen3.7-plus"
    llm_timeout_seconds: float = 60.0
    ocr_lang: str = "ch"
    ocr_backend: str = "rapid"
    scan_backend: str = "hybrid"
    scroll_settle_ms: int = 260
    uia_timeout_seconds: float = 1.5
    screenshot_dir: str = Field(default_factory=lambda: str(data_directory() / "screenshots"))
    keep_screenshots: bool = False

    model_config = SettingsConfigDict(env_file=_environment_file(), extra="ignore")

    @property
    def screenshot_path(self) -> Path:
        return Path(self.screenshot_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
