from __future__ import annotations

from app.core.env_store import RuntimeEnvStore
from app.personal_agent.schemas import SkillManifest, SkillSettingField
from app.personal_agent.settings_store import SkillSettingsStore


def test_runtime_env_store_updates_allow_list_and_preserves_other_lines(tmp_path) -> None:
    path = tmp_path / ".env"
    path.write_text("# keep\nLLM_MODEL=old\nUNRELATED=value\n", encoding="utf-8")
    RuntimeEnvStore(path).update({"LLM_MODEL": "qwen3.7-plus", "OCR_BACKEND": "rapid"})
    content = path.read_text(encoding="utf-8")
    assert "# keep" in content
    assert "UNRELATED=value" in content
    assert "LLM_MODEL=qwen3.7-plus" in content
    assert "OCR_BACKEND=rapid" in content


def test_skill_settings_store_keeps_each_skill_isolated(tmp_path) -> None:
    store = SkillSettingsStore(tmp_path / "skill_settings.json")
    store.save("calendar", {"calendar_id": "work", "reminder": True})
    store.save("notes", {"folder": "inbox"})
    assert store.load("calendar") == {"calendar_id": "work", "reminder": True}
    assert store.load("notes") == {"folder": "inbox"}


def test_skill_manifest_accepts_declarative_settings_schema() -> None:
    manifest = SkillManifest(
        id="calendar",
        name="日程",
        description="test",
        settings_schema=[
            SkillSettingField(key="calendar_id", label="日历 ID"),
            SkillSettingField(key="reminder", label="提醒", kind="boolean", default=True),
        ],
    )
    assert manifest.settings_schema[1].default is True
