from __future__ import annotations

from app.personal_agent.core import PersonalWorkAgent
from app.personal_agent.registry import SkillRegistry
from app.personal_agent.router import IntentRouter
from app.personal_agent.schemas import FollowUpAction, PermissionLevel, SkillManifest, SkillResult
from app.personal_agent.settings_store import AgentPreferences, AgentSettingsStore
from app.personal_agent.skill import Skill, SkillContext
from app.skills.spark_renew.skill import SparkRenewSkill
from app.voice.sapi_gateway import WindowsSapiVoiceGateway
import time


class FakeSkill(Skill):
    manifest = SkillManifest(
        id="spark_scan",
        name="测试火花",
        description="test",
        permission=PermissionLevel.LOCAL_ACTION,
        confirmation_message="确认测试吗？",
    )

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, arguments: dict, context: SkillContext) -> SkillResult:
        self.calls += 1
        return SkillResult(success=True, message="执行成功", data=arguments)


class FakeProvider:
    is_configured = False


class FakeRenewSkill(Skill):
    manifest = SkillManifest(
        id="spark_renew",
        name="测试续火花",
        description="test",
        permission=PermissionLevel.EXTERNAL_WRITE,
        confirmation_message="确认生成计划吗？",
    )

    def __init__(self) -> None:
        self.actions: list[str] = []

    def execute(self, arguments: dict, context: SkillContext) -> SkillResult:
        action = str(arguments["action"])
        self.actions.append(action)
        if action == "direct":
            return SkillResult(success=True, message="已发送 2 人")
        if action == "prepare":
            return SkillResult(
                success=True,
                message="计划 2 人，请再次确认",
                follow_up=FollowUpAction(
                    skill_id="spark_renew",
                    arguments={"action": "send", "token": "once"},
                ),
            )
        return SkillResult(success=True, message="已发送 2 人")


def test_default_wake_word_and_settings_persistence(tmp_path) -> None:
    store = AgentSettingsStore(tmp_path / "settings.json")
    assert store.load().wake_word == "史蒂芬"
    store.save(AgentPreferences(wake_word="小史", voice_enabled=False))
    assert store.load().wake_word == "小史"
    assert store.load().voice_enabled is False


def test_router_uses_fast_skill_path() -> None:
    assert IntentRouter().route("帮我扫描一下火花")[0] == "spark_scan.scan"
    assert IntentRouter().route("续火花")[0] == "spark_renew.prepare"
    assert IntentRouter().route("帮我抖音续个火花")[0] == "spark_renew.prepare"
    assert IntentRouter().route("我们聊聊天吧")[0] == "conversation"


def test_local_skill_requires_confirmation(tmp_path) -> None:
    skill = FakeSkill()
    registry = SkillRegistry()
    registry.register(skill)
    store = AgentSettingsStore(tmp_path / "settings.json")
    agent = PersonalWorkAgent(registry=registry, settings_store=store, provider=FakeProvider())
    first = agent.handle("扫描火花")
    assert first.needs_confirmation
    assert skill.calls == 0
    second = agent.handle("确认")
    assert second.text == "执行成功"
    assert skill.calls == 1


def test_voice_gateway_extracts_command_after_wake_word(tmp_path) -> None:
    store = AgentSettingsStore(tmp_path / "settings.json")
    commands: list[str] = []
    gateway = WindowsSapiVoiceGateway(store, commands.append)
    gateway._process_transcript("史蒂芬，扫描火花")
    assert commands == ["扫描火花"]


def test_wake_word_enters_listening_without_speech_synthesis(tmp_path) -> None:
    store = AgentSettingsStore(tmp_path / "settings.json")
    events: list[str] = []
    gateway = WindowsSapiVoiceGateway(store, lambda _command: None, lambda state, _detail: events.append(state))

    gateway._process_transcript("史蒂芬")

    assert events == ["heard", "listening"]


def test_listening_window_returns_to_idle_after_timeout(tmp_path) -> None:
    store = AgentSettingsStore(tmp_path / "settings.json")
    events: list[str] = []
    gateway = WindowsSapiVoiceGateway(store, lambda _command: None, lambda state, _detail: events.append(state))
    gateway._armed_until = time.monotonic() - 1

    gateway._expire_arm_if_needed()

    assert gateway._armed_until == 0.0
    assert events == ["idle"]


def test_explicit_renew_command_starts_direct_send(tmp_path) -> None:
    skill = FakeRenewSkill()
    registry = SkillRegistry()
    registry.register(skill)
    store = AgentSettingsStore(tmp_path / "settings.json")
    agent = PersonalWorkAgent(registry=registry, settings_store=store, provider=FakeProvider())

    sent = agent.handle("帮我抖音续个火花")
    assert sent.text == "已发送 2 人"
    assert not sent.needs_confirmation
    assert agent.pending is None
    assert skill.actions == ["direct"]


def test_direct_renew_dispatches_single_pass_execution(tmp_path) -> None:
    class SinglePassRenewSkill(SparkRenewSkill):
        def __init__(self) -> None:
            super().__init__(plan_dir=tmp_path)
            self.actions: list[str] = []

        def _direct(self, arguments: dict, context: SkillContext) -> SkillResult:
            self.actions.append("single_pass")
            assert arguments["max_pages"] == 100
            return SkillResult(success=True, message="done")

    skill = SinglePassRenewSkill()
    result = skill.execute({"action": "direct", "max_pages": 100}, SkillContext(progress=lambda _message: None))

    assert result.success
    assert skill.actions == ["single_pass"]
