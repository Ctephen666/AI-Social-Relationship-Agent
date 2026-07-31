from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_user_or_404
from app.database.models import InteractionRecord, Memory, User
from app.database.session import get_db
from app.schemas import InteractionCreate, InteractionRead, MemoryCreate, MemoryRead, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["好友管理"])


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.priority.desc(), User.updated_at.desc())).all())


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    user = get_user_or_404(db, user_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(get_user_or_404(db, user_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/interactions", response_model=list[InteractionRead])
def list_interactions(user_id: int, db: Session = Depends(get_db)) -> list[InteractionRecord]:
    get_user_or_404(db, user_id)
    return list(db.scalars(select(InteractionRecord).where(InteractionRecord.user_id == user_id).order_by(InteractionRecord.time.desc())).all())


@router.post("/{user_id}/interactions", response_model=InteractionRead, status_code=status.HTTP_201_CREATED)
def add_interaction(user_id: int, payload: InteractionCreate, db: Session = Depends(get_db)) -> InteractionRecord:
    get_user_or_404(db, user_id)
    record = InteractionRecord(user_id=user_id, **payload.model_dump(exclude_none=True))
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{user_id}/memories", response_model=list[MemoryRead])
def list_memories(user_id: int, db: Session = Depends(get_db)) -> list[Memory]:
    get_user_or_404(db, user_id)
    return list(db.scalars(select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at.desc())).all())


@router.post("/{user_id}/memories", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
def add_memory(user_id: int, payload: MemoryCreate, db: Session = Depends(get_db)) -> Memory:
    get_user_or_404(db, user_id)
    memory = Memory(user_id=user_id, **payload.model_dump())
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory

