from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import AppSetting, InteractionRecord, ScanTask, User
from app.services.analysis_service import AnalysisService
from app.vision.chat_parser import ChatListParser
from app.vision.ocr_engine import get_ocr_engine
from app.vision.screenshot import ScreenshotService


class ScanService:
    """协调扫描，失败会留下可见任务记录，便于排障。"""

    async def run(self, db: Session, region: tuple[int, int, int, int] | None, source: str = "manual", dry_run: bool = False) -> ScanTask:
        task = ScanTask(status="running", source=source)
        db.add(task)
        db.commit()
        settings = get_settings()
        image_path: Path | None = None
        keep_screenshots = settings.keep_screenshots
        try:
            local_config = db.get(AppSetting, "application")
            configured_region = (local_config.value or {}).get("ocr_region") if local_config else None
            active_region = region or (tuple(configured_region) if configured_region and len(configured_region) == 4 else None)
            keep_screenshots = (local_config.value or {}).get("keep_screenshots", settings.keep_screenshots) if local_config else settings.keep_screenshots
            image_path = ScreenshotService(settings.screenshot_path).capture(active_region)
            task.screenshot_path = str(image_path) if keep_screenshots else None
            blocks = get_ocr_engine(settings.ocr_lang).recognize(image_path)
            observations = ChatListParser().parse(blocks)
            analysis = AnalysisService()
            matched = 0
            for observation in observations:
                user = db.scalar(select(User).where(User.nickname == observation.nickname))
                if user is None:
                    continue
                matched += 1
                db.add(InteractionRecord(
                    user_id=user.id,
                    content=observation.last_message_preview,
                    status=observation.status,
                    source="ocr",
                ))
                if not dry_run and observation.interaction_days is not None:
                    await analysis.analyze_user(db, user, observation.interaction_days, observation.last_message_preview)
            task.status = "completed"
            task.result_count = matched
            task.completed_at = datetime.now()
            db.commit()
        except Exception as error:  # 保留异常到任务记录，不吞掉状态
            task.status = "failed"
            task.error = str(error)
            task.completed_at = datetime.now()
            db.commit()
        finally:
            if image_path and image_path.exists() and not keep_screenshots:
                image_path.unlink(missing_ok=True)
        db.refresh(task)
        return task
