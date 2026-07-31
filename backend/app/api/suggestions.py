from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MessageSuggestion, User
from app.database.session import get_db
from app.schemas import SuggestionRead, SuggestionUpdate

router = APIRouter(prefix="/suggestions", tags=["AI建议"])


def to_read(item: MessageSuggestion, user: User | None) -> SuggestionRead:
    return SuggestionRead.model_validate({**{key: getattr(item, key) for key in SuggestionRead.model_fields if key not in {"nickname"}}, "nickname": user.nickname if user else None})


@router.get("", response_model=list[SuggestionRead])
def list_suggestions(db: Session = Depends(get_db)) -> list[SuggestionRead]:
    rows = db.execute(select(MessageSuggestion, User).join(User, User.id == MessageSuggestion.user_id).order_by(MessageSuggestion.created_at.desc())).all()
    return [to_read(item, user) for item, user in rows]


@router.patch("/{suggestion_id}", response_model=SuggestionRead)
def update_suggestion(suggestion_id: int, payload: SuggestionUpdate, db: Session = Depends(get_db)) -> SuggestionRead:
    item = db.get(MessageSuggestion, suggestion_id)
    if item is None:
        raise HTTPException(status_code=404, detail="建议不存在")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return to_read(item, db.get(User, item.user_id))

