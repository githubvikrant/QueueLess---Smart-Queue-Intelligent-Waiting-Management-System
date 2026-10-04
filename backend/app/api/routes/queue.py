from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.api import EventOut, QueueOut
from app.services import presenter
from app.services.snapshot import build_snapshot

router = APIRouter(prefix="/api", tags=["queue"])


@router.get("/queue", response_model=QueueOut)
@router.get("/queue/", response_model=QueueOut, include_in_schema=False)
def get_queue(db: Session = Depends(get_db)):
    """Dashboard ye call karta hai: saare tokens + counters + ETA."""
    return presenter.build_queue_view(db)


@router.get("/snapshot")
def get_snapshot(db: Session = Depends(get_db)):
    """Raw snapshot (Member 1 ke ETA engine / simulator / agent ke liye)."""
    return build_snapshot(db).to_dict()


@router.get("/events", response_model=list[EventOut])
def get_events(
    limit: int = Query(50, ge=1, le=500),
    correlation_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Audit log timeline (purane se naye)."""
    return presenter.list_events(db, limit, correlation_id)
