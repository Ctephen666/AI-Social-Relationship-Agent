from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.tasks import scheduled_scan


_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def configure_scan_job(scan_time: str = "09:00", frequency: str = "daily") -> None:
    """更新计划而不重启服务；manual 表示关闭自动扫描。"""
    _scheduler.remove_job("daily_social_scan") if _scheduler.get_job("daily_social_scan") else None
    if frequency != "daily":
        return
    hour, minute = (int(value) for value in scan_time.split(":", maxsplit=1))
    _scheduler.add_job(scheduled_scan, CronTrigger(hour=hour, minute=minute), id="daily_social_scan", replace_existing=True)


def build_scheduler() -> BackgroundScheduler:
    configure_scan_job()
    return _scheduler
