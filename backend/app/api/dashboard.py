from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import InteractionRecord, MessageSuggestion, Priority, SuggestionStatus, User
from app.database.session import get_db
from app.schemas import DashboardRead, InteractionRead, UserRead

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("", response_model=DashboardRead)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardRead:
    cutoff = datetime.now() - timedelta(days=7)
    active_ids = select(InteractionRecord.user_id).where(InteractionRecord.time >= cutoff)
    needing = db.scalar(select(func.count(User.id)).where(User.id.not_in(active_ids))) or 0
    high = list(db.scalars(select(User).where(User.priority == Priority.high).order_by(User.updated_at.desc()).limit(6)).all())
    pending = db.scalar(select(func.count(MessageSuggestion.id)).where(MessageSuggestion.status == SuggestionStatus.pending)) or 0
    recent = list(db.scalars(select(InteractionRecord).order_by(InteractionRecord.time.desc()).limit(8)).all())
    return DashboardRead(
        today_needing_attention=needing,
        high_priority_users=[UserRead.model_validate(item) for item in high],
        pending_suggestions=pending,
        recent_interactions=[InteractionRead.model_validate(item) for item in recent],
    )

