from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import AppSetting
from app.database.session import get_db
from app.scheduler.scheduler import configure_scan_job
from app.schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["设置"])
SETTINGS_KEY = "application"


def current(db: Session) -> AppSetting:
    setting = db.get(AppSetting, SETTINGS_KEY)
    if setting is None:
        setting = AppSetting(key=SETTINGS_KEY, value={})
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.get("", response_model=SettingsRead)
def get_settings_endpoint(db: Session = Depends(get_db)) -> SettingsRead:
    values = current(db).value
    config = get_settings()
    return SettingsRead(**values, keep_screenshots=values.get("keep_screenshots", config.keep_screenshots), llm_configured=bool(config.llm_api_key and config.llm_model))


@router.put("", response_model=SettingsRead)
def update_settings_endpoint(payload: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsRead:
    setting = current(db)
    values = {**setting.value, **payload.model_dump(exclude_unset=True)}
    setting.value = values
    db.commit()
    configure_scan_job(values.get("scan_time", "09:00"), values.get("scan_frequency", "daily"))
    return get_settings_endpoint(db)
