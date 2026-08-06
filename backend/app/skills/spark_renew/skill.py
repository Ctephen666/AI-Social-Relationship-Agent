from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import time
import uuid

from app.core.runtime import data_directory
from app.database.session import SessionLocal
from app.personal_agent.schemas import FollowUpAction, PermissionLevel, SkillManifest, SkillResult
from app.personal_agent.settings_store import AgentSettingsStore
from app.personal_agent.skill import Skill, SkillContext


class SparkRenewSkill(Skill):
    """Narrowly scoped batch-message Skill with one-time plans.

    An explicit renew intent may run both stages in one call. The persisted
    plan and one-time token still prevent replay and constrain every send to
    the exact contacts found by the preceding scan.
    """

    manifest = SkillManifest(
        id="spark_renew",
        name="续火花发送",
        description="收到明确续火花指令后，扫描抖音聊天列表并限速逐人发送。",
        permission=PermissionLevel.EXTERNAL_WRITE,
        confirmation_message="我会先扫描全部聊天联系人并生成发送预览，不会立刻发送。确认开始扫描吗？",
        examples=["续火花", "给所有好友续一下火花"],
    )

    PLAN_TTL_SECONDS = 15 * 60

    def __init__(self, settings_store: AgentSettingsStore | None = None, plan_dir: Path | None = None) -> None:
        self.settings_store = settings_store or AgentSettingsStore()
        self.plan_dir = plan_dir or data_directory() / "pending_actions"
        self._tokens: dict[str, str] = {}

    def execute(self, arguments: dict, context: SkillContext) -> SkillResult:
        action = str(arguments.get("action", "prepare"))
        if action == "direct":
            return self._direct(arguments, context)
        if action == "prepare":
            return self._prepare(arguments, context)
        if action == "send":
            return self._send(arguments, context)
        raise ValueError(f"不支持的续火花动作：{action}")

    def _direct(self, arguments: dict, context: SkillContext) -> SkillResult:
        """Open Messages and scan/send each row once for minimum latency."""
        from app.services.douyin_spark_renew_service import DouyinSparkRenewService

        preferences = self.settings_store.load()
        max_pages = max(1, min(int(arguments.get("max_pages", 30)), 100))
        plan_id = uuid.uuid4().hex
        now = time.time()
        plan = {
            "version": 2,
            "plan_id": plan_id,
            "state": "sending",
            "mode": "single_pass",
            "created_at": datetime.now(UTC).isoformat(),
            "created_timestamp": now,
            "expires_timestamp": now + self.PLAN_TTL_SECONDS,
            "message": preferences.spark_renew_message,
            "delay_seconds": preferences.spark_renew_delay_seconds,
            "max_pages": max_pages,
            "max_recipients": preferences.spark_renew_max_recipients,
        }
        self._save_plan(plan)
        db = SessionLocal()
        try:
            summary = DouyinSparkRenewService().send_all(
                db=db,
                plan_id=plan_id,
                message_template=preferences.spark_renew_message,
                delay_seconds=preferences.spark_renew_delay_seconds,
                max_pages=max_pages,
                max_recipients=preferences.spark_renew_max_recipients,
                progress=context.progress,
            )
        except Exception:
            plan["state"] = "failed"
            self._save_plan(plan)
            raise
        finally:
            db.close()
        plan["state"] = "aborted" if summary.aborted else "completed"
        plan["result"] = {
            "sent": summary.sent,
            "failed": summary.failed,
            "not_found": summary.not_found,
            "elapsed_ms": summary.elapsed_ms,
        }
        self._save_plan(plan)
        state_text = "已按快捷键停止" if summary.aborted else "已完成"
        return SkillResult(
            success=not summary.aborted and summary.failed == 0,
            message=f"续火花发送{state_text}：成功 {summary.sent} 人，失败 {summary.failed} 人。",
            data=plan["result"] | {"aborted": summary.aborted, "plan_id": plan_id},
        )

    def _prepare(self, arguments: dict, context: SkillContext) -> SkillResult:
        # Heavy vision imports remain lazy so the desktop companion starts fast.
        from app.services.douyin_spark_scan_service import DouyinSparkScanService

        preferences = self.settings_store.load()
        max_pages = max(1, min(int(arguments.get("max_pages", 30)), 100))
        db = SessionLocal()
        try:
            summary = DouyinSparkScanService().run_full_scan(db, max_pages=max_pages, progress=context.progress)
        finally:
            db.close()

        recipients: list[dict[str, str]] = []
        seen: set[str] = set()
        for record in summary.results:
            nickname = record.nickname.strip()
            identity = self._identity(nickname)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            message = preferences.spark_renew_message.replace("{nickname}", nickname)
            recipients.append({"nickname": nickname, "message": message})
            if len(recipients) >= preferences.spark_renew_max_recipients:
                break
        if not recipients:
            return SkillResult(success=False, message="没有识别到可发送的聊天联系人。")

        plan_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(24)
        now = time.time()
        plan = {
            "version": 1,
            "plan_id": plan_id,
            "state": "prepared",
            "created_at": datetime.now(UTC).isoformat(),
            "created_timestamp": now,
            "expires_timestamp": now + self.PLAN_TTL_SECONDS,
            "recipients": recipients,
            "delay_seconds": preferences.spark_renew_delay_seconds,
            "max_pages": max_pages,
        }
        self._save_plan(plan)
        self._tokens[plan_id] = token
        names = "、".join(item["nickname"] for item in recipients[:8])
        remainder = len(recipients) - min(8, len(recipients))
        preview_suffix = f"，以及另外 {remainder} 人" if remainder else ""
        message_preview = recipients[0]["message"]
        return SkillResult(
            success=True,
            message=(
                f"发送计划已生成：共 {len(recipients)} 人；消息为“{message_preview}”；"
                f"对象包括 {names}{preview_suffix}。这是最后确认，确认后将真实发送；"
                "发送中可按 Ctrl+Shift+Q 紧急停止。请说“确认”或“取消”。"
            ),
            data={"plan_id": plan_id, "recipient_count": len(recipients), "message": message_preview},
            follow_up=FollowUpAction(
                skill_id="spark_renew",
                arguments={"action": "send", "plan_id": plan_id, "token": token},
            ),
        )

    def _send(self, arguments: dict, context: SkillContext) -> SkillResult:
        plan_id = str(arguments.get("plan_id", ""))
        token = str(arguments.get("token", ""))
        expected = self._tokens.pop(plan_id, None)
        if not expected or not secrets.compare_digest(token, expected):
            raise PermissionError("发送计划令牌无效或已使用，请重新说“续火花”生成计划。")
        plan = self._load_plan(plan_id)
        if plan.get("state") != "prepared":
            raise PermissionError("发送计划不是待确认状态，已拒绝重复执行。")
        if time.time() > float(plan.get("expires_timestamp", 0)):
            plan["state"] = "expired"
            self._save_plan(plan)
            raise PermissionError("发送计划已超过 15 分钟，请重新扫描确认。")

        plan["state"] = "sending"
        self._save_plan(plan)
        from app.services.douyin_spark_renew_service import DouyinSparkRenewService, RenewalRecipient

        recipients = [RenewalRecipient(**item) for item in plan["recipients"]]
        db = SessionLocal()
        try:
            summary = DouyinSparkRenewService().send(
                db=db,
                plan_id=plan_id,
                recipients=recipients,
                delay_seconds=float(plan["delay_seconds"]),
                max_pages=int(plan["max_pages"]),
                progress=context.progress,
            )
        except Exception:
            plan["state"] = "failed"
            self._save_plan(plan)
            raise
        finally:
            db.close()

        plan["state"] = "aborted" if summary.aborted else "completed"
        plan["result"] = {
            "sent": summary.sent,
            "failed": summary.failed,
            "not_found": summary.not_found,
            "elapsed_ms": summary.elapsed_ms,
        }
        self._save_plan(plan)
        state_text = "已按快捷键停止" if summary.aborted else "已完成"
        return SkillResult(
            success=not summary.aborted and summary.failed == 0 and summary.not_found == 0,
            message=(
                f"续火花发送{state_text}：成功 {summary.sent} 人，失败 {summary.failed} 人，"
                f"未在列表中找到 {summary.not_found} 人。"
            ),
            data=plan["result"] | {"aborted": summary.aborted, "plan_id": plan_id},
        )

    def _save_plan(self, plan: dict) -> None:
        self.plan_dir.mkdir(parents=True, exist_ok=True)
        path = self.plan_dir / f"spark_renew_{plan['plan_id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _load_plan(self, plan_id: str) -> dict:
        if not plan_id or any(character not in "0123456789abcdef" for character in plan_id):
            raise PermissionError("发送计划编号无效。")
        path = self.plan_dir / f"spark_renew_{plan_id}.json"
        if not path.is_file():
            raise FileNotFoundError("发送计划不存在，请重新扫描。")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _identity(value: str) -> str:
        return "".join(value.replace("…", "").replace(".", "").casefold().split())
