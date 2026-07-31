from __future__ import annotations

import httpx

from app.core.config import get_settings


class LLMProvider:
    """OpenAI Chat Completions 兼容提供方；未配置时不发起网络请求。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.llm_base_url and self.settings.llm_api_key and self.settings.llm_model)

    async def complete(self, system: str, prompt: str) -> str | None:
        if not self.is_configured:
            return None
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.75,
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()

