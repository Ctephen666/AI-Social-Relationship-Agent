from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.models import User


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="好友不存在")
    return user

