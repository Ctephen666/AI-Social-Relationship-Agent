from __future__ import annotations

from sqlalchemy import desc, select

from app.database.models import DesktopSparkScan
from app.database.session import SessionLocal
from app.personal_agent.schemas import PermissionLevel, SkillManifest, SkillResult
from app.personal_agent.skill import Skill, SkillContext
class SparkScanSkill(Skill):
    manifest = SkillManifest(
        id="spark_scan",
        name="续火花",
        description="安全打开抖音消息列表、滚动扫描并识别好友火花，不进入聊天、不发送消息。",
        permission=PermissionLevel.LOCAL_ACTION,
        confirmation_message="我将打开抖音并滚动聊天列表，只读取火花状态，不会发送消息。确认开始吗？",
        examples=["扫描一下火花", "看看哪些火花快断了", "检查抖音火花"],
    )

    def execute(self, arguments: dict, context: SkillContext) -> SkillResult:
        action = str(arguments.get("action", "scan"))
        if action == "latest":
            return self._latest()
        # Desktop startup must stay instant.  The vision stack imports ONNX
        # Runtime and OCR models, so load it only when a scan is confirmed.
        from app.services.douyin_spark_scan_service import DouyinSparkScanService

        max_pages = max(1, min(int(arguments.get("max_pages", 30)), 100))
        db = SessionLocal()
        try:
            summary = DouyinSparkScanService().run_full_scan(db, max_pages=max_pages, progress=context.progress)
            active = sum(row.spark_status.value == "active" for row in summary.results)
            gray = sum(row.spark_status.value == "gray" for row in summary.results)
            none = len(summary.results) - active - gray
            return SkillResult(
                success=True,
                message=(
                    f"火花扫描完成。共识别 {len(summary.results)} 位好友，"
                    f"活跃 {active} 位，灰色 {gray} 位，未检测到火花 {none} 位，"
                    f"用时 {summary.elapsed_ms / 1000:.1f} 秒。"
                ),
                data={
                    "pages": summary.pages_scanned,
                    "contacts": len(summary.results),
                    "active": active,
                    "gray": gray,
                    "none": none,
                    "elapsed_ms": summary.elapsed_ms,
                    "scan_mode": summary.scan_mode,
                },
            )
        finally:
            db.close()

    @staticmethod
    def _latest() -> SkillResult:
        db = SessionLocal()
        try:
            latest = db.scalar(select(DesktopSparkScan).order_by(desc(DesktopSparkScan.created_at)).limit(1))
            if latest is None:
                return SkillResult(success=True, message="还没有火花扫描记录。", data={})
            return SkillResult(
                success=True,
                message=f"最近一次记录：{latest.nickname} 的火花状态是 {latest.spark_status.value}。",
                data={"nickname": latest.nickname, "status": latest.spark_status.value, "created_at": str(latest.created_at)},
            )
        finally:
            db.close()
