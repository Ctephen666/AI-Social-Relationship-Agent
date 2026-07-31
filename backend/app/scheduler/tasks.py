import asyncio
import logging

from app.database.session import SessionLocal
from app.services.scan_service import ScanService

logger = logging.getLogger(__name__)


def scheduled_scan() -> None:
    """APScheduler 同步入口；扫描本身仍是异步业务服务。"""
    db = SessionLocal()
    try:
        asyncio.run(ScanService().run(db, region=None, source="scheduler"))
    except Exception:
        logger.exception("定时扫描执行失败")
    finally:
        db.close()

