"""Queue snapshot: DB se nikla plain, immutable data.
Member 1 ka ETA engine, what-if simulator aur LLM agent sab isi pe chalenge.
Copy karke (dataclasses.replace) scenario lagao, asli DB ko kabhi touch mat karo."""
import json
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models import Counter, Service, Token


@dataclass(frozen=True)
class ServiceSnap:
    code: str
    name: str
    avg_duration_min: float


@dataclass(frozen=True)
class CounterSnap:
    code: str
    name: str
    is_open: bool
    speed_factor: float
    injected_delay_min: float
    service_codes: tuple[str, ...]


@dataclass(frozen=True)
class TokenSnap:
    code: str
    patient_name: str
    service_code: str
    counter_code: str | None
    status: str
    priority: int
    is_walk_in: bool
    created_at: datetime
    called_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    actual_duration_min: float | None
    last_change_reason: str | None


@dataclass(frozen=True)
class QueueSnapshot:
    now: datetime
    services: tuple[ServiceSnap, ...]
    counters: tuple[CounterSnap, ...]
    tokens: tuple[TokenSnap, ...]

    def service(self, code: str) -> ServiceSnap:
        return next(s for s in self.services if s.code == code)

    def counter(self, code: str) -> CounterSnap:
        return next(c for c in self.counters if c.code == code)

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=lambda o: o.isoformat()))


def build_snapshot(db: Session) -> QueueSnapshot:
    services = db.scalars(select(Service).order_by(Service.id)).all()
    counters = db.scalars(select(Counter).order_by(Counter.id)).all()
    tokens = db.scalars(select(Token).order_by(Token.id)).all()
    return QueueSnapshot(
        now=clock.now(),
        services=tuple(ServiceSnap(s.code, s.name, s.avg_duration_min) for s in services),
        counters=tuple(
            CounterSnap(
                c.code, c.name, c.is_open, c.speed_factor, c.injected_delay_min,
                tuple(c.service_codes),
            )
            for c in counters
        ),
        tokens=tuple(
            TokenSnap(
                t.code, t.patient_name, t.service.code,
                t.counter.code if t.counter else None,
                t.status.value, t.priority, t.is_walk_in,
                clock.as_utc(t.created_at), clock.as_utc(t.called_at),
                clock.as_utc(t.started_at), clock.as_utc(t.completed_at),
                t.actual_duration_min, t.last_change_reason,
            )
            for t in tokens
        ),
    )
