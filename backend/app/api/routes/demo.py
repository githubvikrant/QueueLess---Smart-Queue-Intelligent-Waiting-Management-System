import random

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import correlation_id
from app.core import clock
from app.db.session import get_db
from app.models import Service
from app.schemas.api import AdvanceClockRequest, CounterOut, DelayRequest, QueueOut, WalkInRequest
from app.seeding.data import WALK_IN_NAMES
from app.seeding.seeder import reseed
from app.services import lifecycle, presenter, publisher
from app.services.events import log_event
from app.services.publisher import publish_queue

router = APIRouter(prefix="/api/demo", tags=["demo controls"])


@router.get("/clock")
def get_clock():
    return {"now": clock.now()}


@router.post("/inject-delay", response_model=CounterOut)
async def inject_delay(body: DelayRequest, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """Demo: 'Counter A pe +12 min delay'."""
    c = lifecycle.inject_delay(db, body.counter_code, body.minutes, corr)
    await publish_queue(db, corr, f"Delay +{body.minutes:g} min on Counter {c.code}")
    return next(x for x in presenter.build_queue_view(db).counters if x.code == c.code)


@router.post("/walk-ins", response_model=QueueOut)
async def add_walk_ins(body: WalkInRequest, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """Demo: 5 walk-in patients ek saath (deterministic random services)."""
    services = [s.code for s in db.scalars(select(Service).order_by(Service.id))]
    existing = len(presenter.build_queue_view(db).tokens)
    rng = random.Random(existing)
    for i in range(body.count):
        lifecycle.create_token(
            db, corr, WALK_IN_NAMES[(existing + i) % len(WALK_IN_NAMES)],
            rng.choice(services), is_walk_in=True,
        )
    log_event(db, "demo.walk_ins_added", corr, payload={"count": body.count})
    db.commit()
    await publish_queue(db, corr, f"{body.count} walk-ins added")
    return presenter.build_queue_view(db)


@router.post("/advance-clock")
async def advance_clock(body: AdvanceClockRequest, db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """Demo clock aage badhao (e.g. 10 min). ETA aur elapsed time isi se chalte hain."""
    now = clock.advance(body.minutes)
    log_event(db, "demo.clock_advanced", corr, payload={"minutes": body.minutes})
    db.commit()
    await publish_queue(db, corr, f"Clock advanced {body.minutes:g} min")
    return {"now": now}


@router.post("/reset", response_model=QueueOut)
async def reset(db: Session = Depends(get_db), corr: str = Depends(correlation_id)):
    """Poora demo CityCare ke starting state pe wapas."""
    reseed(db)
    publisher.reset_tracking()
    log_event(db, "demo.reset", corr)
    db.commit()
    await publish_queue(db, corr, "Demo reset")
    return presenter.build_queue_view(db)
