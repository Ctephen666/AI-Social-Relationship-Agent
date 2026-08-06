from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.personal_agent.schemas import SkillManifest, SkillResult


@dataclass(frozen=True)
class SkillContext:
    progress: Callable[[str], None]


class Skill(ABC):
    manifest: SkillManifest

    @abstractmethod
    def execute(self, arguments: dict[str, Any], context: SkillContext) -> SkillResult:
        """Execute one allow-listed capability and return structured output."""
