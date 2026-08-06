from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
import threading
from typing import Any

from app.llm.provider import LLMProvider
from app.personal_agent.policy import PermissionPolicy
from app.personal_agent.registry import SkillRegistry
from app.personal_agent.router import IntentRouter
from app.personal_agent.schemas import AgentReply, PendingAction
from app.personal_agent.settings_store import AgentSettingsStore
from app.personal_agent.skill import SkillContext
from app.skills.spark_renew import SparkRenewSkill
from app.skills.spark_scan import SparkScanSkill


EventSink = Callable[[str, dict[str, Any]], None]


class PersonalWorkAgent:
    """Single low-latency agent core with deterministic skills and LLM fallback."""

    CONFIRM_WORDS = {"确认", "确定", "开始", "执行", "可以", "好的", "好", "继续"}
    CANCEL_WORDS = {"取消", "不要", "停止", "算了", "不用"}

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        settings_store: AgentSettingsStore | None = None,
        provider: LLMProvider | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        if not self.registry.manifests():
            self.registry.register(SparkScanSkill())
            self.registry.register(SparkRenewSkill())
        self.settings_store = settings_store or AgentSettingsStore()
        self.provider = provider or LLMProvider()
        self.router = IntentRouter()
        self.event_sink = event_sink or (lambda _event, _payload: None)
        self.pending: PendingAction | None = None
        self.history: deque[tuple[str, str]] = deque(maxlen=16)
        self._lock = threading.RLock()

    def handle(self, text: str) -> AgentReply:
        cleaned = text.strip()
        if not cleaned:
            return AgentReply(text="我没有听清，可以再说一次吗？", state="listening")
        with self._lock:
            self.history.append(("user", cleaned))
            compact = "".join(cleaned.split())
            if self.pending is not None:
                if compact in self.CONFIRM_WORDS:
                    action = self.pending
                    self.pending = None
                    return self._execute(action.skill_id, action.arguments)
                if compact in self.CANCEL_WORDS:
                    self.pending = None
                    return self._remember(AgentReply(text="好的，已经取消。", intent="system.cancelled"))
                return self._remember(AgentReply(text="请说“确认”开始执行，或者说“取消”。", state="confirming", needs_confirmation=True))

            intent, arguments = self.router.route(cleaned)
            if intent == "system.help":
                names = "、".join(item.name for item in self.registry.manifests())
                return self._remember(AgentReply(text=f"我目前支持：{names}。你也可以和我语音对话。", intent=intent))
            if intent == "system.settings":
                self.event_sink("open_settings", {})
                return self._remember(AgentReply(text="已经为你打开设置。", intent=intent))
            if intent == "spark_scan.latest":
                return self._execute("spark_scan", {"action": "latest"}, bypass_confirmation=True)
            if intent == "spark_scan.scan":
                return self.request_skill("spark_scan", arguments)
            if intent == "spark_renew.prepare":
                # Saying an explicit renew command is the user's authorization
                # for this narrowly scoped Skill. The Skill still verifies the
                # Douyin conversation/editor, rate-limits, audits and supports
                # the emergency-stop shortcut before every external write.
                return self._execute("spark_renew", {"action": "direct", **arguments})
            return self._conversation(cleaned)

    def request_skill(self, skill_id: str, arguments: dict[str, Any], confirmed: bool = False) -> AgentReply:
        skill = self.registry.get(skill_id)
        preferences = self.settings_store.load()
        policy = PermissionPolicy(preferences.require_confirmation)
        if not confirmed and policy.requires_confirmation(skill.manifest.permission):
            self.pending = PendingAction(skill_id=skill_id, arguments=arguments)
            text = skill.manifest.confirmation_message or f"确认执行 {skill.manifest.name} 吗？"
            self.event_sink("confirmation_required", {"skill_id": skill_id})
            return self._remember(AgentReply(text=text, intent=skill_id, state="confirming", needs_confirmation=True))
        return self._execute(skill_id, arguments)

    def _execute(self, skill_id: str, arguments: dict[str, Any], bypass_confirmation: bool = False) -> AgentReply:
        skill = self.registry.get(skill_id)
        self.event_sink("skill_started", {"skill_id": skill_id})
        try:
            result = skill.execute(arguments, SkillContext(progress=lambda message: self.event_sink("progress", {"message": message})))
        except Exception as exc:
            self.event_sink("skill_failed", {"skill_id": skill_id, "error": str(exc)})
            return self._remember(AgentReply(text=f"{skill.manifest.name}执行失败：{exc}", intent=skill_id, state="error"))
        self.event_sink("skill_finished", {"skill_id": skill_id, "success": result.success, "data": result.data})
        if result.success and result.follow_up is not None:
            self.pending = PendingAction(
                skill_id=result.follow_up.skill_id,
                arguments=result.follow_up.arguments,
            )
            self.event_sink("confirmation_required", {"skill_id": result.follow_up.skill_id, "external_write": True})
            return self._remember(
                AgentReply(
                    text=result.message,
                    intent=skill_id,
                    state="confirming",
                    needs_confirmation=True,
                    data=result.data,
                )
            )
        return self._remember(AgentReply(text=result.message, intent=skill_id, state="success" if result.success else "error", data=result.data))

    def _conversation(self, text: str) -> AgentReply:
        if not self.provider.is_configured:
            return self._remember(
                AgentReply(
                    text="我已经听到了。当前还没有配置对话模型，但火花扫描等本地 Skill 可以正常使用。你可以在 backend 的 .env 中配置兼容模型。",
                    intent="conversation.unconfigured",
                )
            )
        context = "\n".join(f"{role}: {content}" for role, content in list(self.history)[-8:])
        try:
            answer = asyncio.run(
                self.provider.complete(
                    "你叫史蒂芬，是运行在用户 Windows 电脑上的个人工作助手。回答简洁自然。不得声称执行了未调用的工具；只有明确匹配且受权限约束的 Skill 才能执行写入、发送或删除。",
                    f"最近对话：\n{context}\n\n用户当前输入：{text}",
                )
            )
        except Exception as exc:
            return self._remember(AgentReply(text=f"对话模型暂时不可用：{exc}", intent="conversation.error", state="error"))
        return self._remember(AgentReply(text=answer or "我暂时没有生成有效回答。", intent="conversation"))

    def _remember(self, reply: AgentReply) -> AgentReply:
        self.history.append(("assistant", reply.text))
        return reply
