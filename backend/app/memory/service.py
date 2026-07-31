from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Memory


class MemoryService:
    def recent_context(self, db: Session, user_id: int, limit: int = 5) -> list[str]:
        rows = db.scalars(
            select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at.desc()).limit(limit)
        ).all()
        return [f"{row.facts} {row.preferences}".strip() for row in reversed(rows)]

