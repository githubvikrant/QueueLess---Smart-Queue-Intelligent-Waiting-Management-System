from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import correlation_id
from app.db.session import get_db
from app.schemas.api import CounterCreate, CounterOut, QueueOut, TokenOut
from app.services import lifecycle, presenter
from app.services.publisher import publish_queue

router = APIRouter(prefix="/api/counters", tags=["counters"])


def _counter_out(db: Session, code: str) -> CounterOut:
    return next(c for c in presenter.build_queue_view(db).counters if c.code == code.upper())


@router.get("", response_model=list[CounterOut])
def list_counters(db: Session = Depends(get_db)):
    return presenter.build_queue_view(db).counters


@router.post("", response_model=CounterOut, status_code=201)
async def create_counter(body: CounterCreate, db: Session = Depends(get_db),
                         corr: str = Depends(correlation_id)):
    """Naya counter (jaise Counter C). is_open=true bhejo to turant khul jata hai."""
    c = lifecycle.create_counter(db, body.code, body.name, body.services, body.is_open, body.speed_factor, corr)
    await publish_queue(db, corr, f"Counter {c.code} created")
    return _counter_out(db, c.code)


@router.post("/{code}/open", response_model=CounterOut)
async def open_counter(code: str, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    c = lifecycle.open_counter(db, code, corr)
    await publish_queue(db, corr, f"Counter {c.code} opened")
    return _counter_out(db, c.code)


@router.post("/{code}/close", response_model=CounterOut)
async def close_counter(code: str, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """Counter band: waiting tokens eligible counter pe auto-shift, baaki 'waiting for counter'."""
    c = lifecycle.close_counter(db, code, corr)
    await publish_queue(db, corr, f"Counter {c.code} closed")
    return _counter_out(db, c.code)


@router.post("/{code}/call-next", response_model=TokenOut)
async def call_next(code: str, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """Is counter ki line ka agla token (priority pehle, phir FIFO) call karo."""
    token = lifecycle.call_next(db, code, corr)
    await publish_queue(db, corr, f"{token.code} called")
    return presenter.token_view(db, token.code)


@router.post("/{code}/advance", response_model=QueueOut)
async def advance_counter(code: str, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """
    One-click advance: complete current patient (if any) + call next + auto-start.
    Manager sirf yeh ek button dabaye — baki sab automatic.
    """
    lifecycle.advance_counter(db, code, corr)
    await publish_queue(db, corr, f"Counter {code.upper()} advanced")
    return presenter.build_queue_view(db)
