from __future__ import annotations

import json
from pathlib import Path
import threading

from pydantic import BaseModel, Field

from app.core.runtime import data_directory


class AgentPreferences(BaseModel):
    wake_word: str = Field(default="史蒂芬", min_length=1, max_length=20)
    voice_enabled: bool = True
    require_confirmation: bool = True
    listen_timeout_seconds: int = Field(default=8, ge=3, le=30)
    asr_backend: str = Field(default="sensevoice", pattern=r"^(sensevoice|sapi)$")
    spark_renew_message: str = Field(default="来续个火花～", min_length=1, max_length=120)
    spark_renew_max_recipients: int = Field(default=300, ge=1, le=300)
    spark_renew_delay_seconds: float = Field(default=0.25, ge=0.15, le=3.0)


class AgentSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_directory() / "agent_settings.json"
        self._lock = threading.RLock()

    def load(self) -> AgentPreferences:
        with self._lock:
            if not self.path.is_file():
                return AgentPreferences()
            try:
                return AgentPreferences.model_validate_json(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                return AgentPreferences()

    def save(self, preferences: AgentPreferences) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(preferences.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(self.path)


class SkillSettingsStore:
    """Thread-safe JSON store for settings declared by installable Skills."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_directory() / "skill_settings.json"
        self._lock = threading.RLock()

    def load(self, skill_id: str) -> dict:
        with self._lock:
            payload = self._read_all()
            value = payload.get(skill_id, {})
            return dict(value) if isinstance(value, dict) else {}

    def save(self, skill_id: str, values: dict) -> None:
        with self._lock:
            payload = self._read_all()
            payload[skill_id] = values
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)

    def _read_all(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
