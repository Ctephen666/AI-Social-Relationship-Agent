from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ScanTask
from app.database.session import get_db
from app.schemas import ScanRead, ScanRequest
from app.services.scan_service import ScanService

router = APIRouter(prefix="/scans", tags=["视觉扫描"])


@router.get("", response_model=list[ScanRead])
def list_scans(db: Session = Depends(get_db)) -> list[ScanTask]:
    return list(db.scalars(select(ScanTask).order_by(ScanTask.created_at.desc()).limit(30)).all())


@router.post("", response_model=ScanRead, status_code=status.HTTP_201_CREATED)
async def run_scan(payload: ScanRequest, db: Session = Depends(get_db)) -> ScanTask:
    return await ScanService().run(db, payload.region, dry_run=payload.dry_run)

