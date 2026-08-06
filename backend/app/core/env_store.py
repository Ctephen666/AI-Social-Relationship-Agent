from __future__ import annotations

from pathlib import Path
import re
import threading
from typing import Any

from app.core.config import environment_file_path, get_settings


class RuntimeEnvStore:
    """Small atomic editor for the allow-listed runtime settings in `.env`."""

    ALLOWED_KEYS = {
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "OCR_BACKEND",
        "SCAN_BACKEND",
        "SCROLL_SETTLE_MS",
    }

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or environment_file_path()
        self._lock = threading.RLock()

    def update(self, values: dict[str, Any]) -> None:
        unknown = set(values) - self.ALLOWED_KEYS
        if unknown:
            raise ValueError(f"不允许写入的配置项：{', '.join(sorted(unknown))}")
        normalized: dict[str, str] = {}
        for key, value in values.items():
            text = str(value).strip()
            if "\n" in text or "\r" in text:
                raise ValueError(f"{key} 不能包含换行。")
            normalized[key] = text

        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.is_file() else []
            found: set[str] = set()
            output: list[str] = []
            pattern = re.compile(r"^([A-Z][A-Z0-9_]*)=")
            for line in lines:
                match = pattern.match(line)
                key = match.group(1) if match else ""
                if key in normalized:
                    output.append(f"{key}={normalized[key]}")
                    found.add(key)
                else:
                    output.append(line)
            for key, value in normalized.items():
                if key not in found:
                    output.append(f"{key}={value}")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
            temporary.replace(self.path)
            get_settings.cache_clear()
