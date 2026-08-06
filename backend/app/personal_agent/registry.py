from __future__ import annotations

from app.personal_agent.skill import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.manifest.id in self._skills:
            raise ValueError(f"Skill 已注册：{skill.manifest.id}")
        self._skills[skill.manifest.id] = skill

    def get(self, skill_id: str) -> Skill:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise KeyError(f"未知 Skill：{skill_id}") from exc

    def manifests(self):
        return [skill.manifest for skill in self._skills.values()]
