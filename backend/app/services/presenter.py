"""Snapshot + ETA -> API ke liye JSON-ready views."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import Event
from app.schemas.api import CounterOut, EventOut, QueueOut, QueueStats, TokenOut
from app.services.eta import EtaRange, compute_etas, projected_wait
from app.services.snapshot import QueueSnapshot, TokenSnap, build_snapshot

ACTIVE = ("called", "in_service")


def _eta_text(t: TokenSnap, eta: EtaRange | None) -> str:
    if t.status == "in_service":
        return "Being served now"
    if t.status == "called":
        return f"Please go to Counter {t.counter_code} now"
    if t.status == "completed":
        return "Completed"
    if t.status == "no_show":
        return "Marked as no-show. Please contact the reception"
    if t.status == "skipped":
        return "Skipped. Please contact the reception"
    if eta is None:
        return "Waiting for a counter"
    return f"about {eta.eta_min}-{eta.eta_max} minutes"


def view_from_snapshot(snap: QueueSnapshot, etas: dict[str, EtaRange]) -> QueueOut:
    svc_name = {s.code: s.name for s in snap.services}
    tokens = []
    for t in snap.tokens:
        eta = etas.get(t.code)
        tokens.append(TokenOut(
            code=t.code, patient_name=t.patient_name, service_code=t.service_code,
            service_name=svc_name[t.service_code], counter_code=t.counter_code,
            status=t.status, priority=t.priority, is_walk_in=t.is_walk_in,
            position=eta.position if eta else None,
            eta_minutes=eta.eta_minutes if eta else None,
            eta_min=eta.eta_min if eta else None,
            eta_max=eta.eta_max if eta else None,
            eta_text=_eta_text(t, eta), last_change_reason=t.last_change_reason,
            created_at=t.created_at, called_at=t.called_at,
            started_at=t.started_at, completed_at=t.completed_at,
        ))
    counters = []
    for c in snap.counters:
        mine = [t for t in snap.tokens if t.counter_code == c.code]
        active = next((t.code for t in mine if t.status in ACTIVE), None)
        counters.append(CounterOut(
            code=c.code, name=c.name, is_open=c.is_open, speed_factor=c.speed_factor,
            injected_delay_min=c.injected_delay_min, service_codes=list(c.service_codes),
            current_token=active,
            waiting_count=sum(t.status == "waiting" for t in mine),
            projected_wait_min=round(projected_wait(snap, c.code), 1) if c.is_open else 0.0,
        ))
    count = lambda s: sum(t.status == s for t in snap.tokens)  # noqa: E731
    stats = QueueStats(
        total=len(snap.tokens), waiting=count("waiting"), called=count("called"),
        in_service=count("in_service"), completed=count("completed"),
        no_show=count("no_show"), skipped=count("skipped"),
    )
    return QueueOut(now=snap.now, counters=counters, tokens=tokens, stats=stats)


def build_queue_view(db: Session) -> QueueOut:
    snap = build_snapshot(db)
    return view_from_snapshot(snap, compute_etas(snap))


def token_view(db: Session, code: str) -> TokenOut:
    for t in build_queue_view(db).tokens:
        if t.code == code.upper():
            return t
    raise NotFound(f"Token {code} not found")


def event_out(ev: Event) -> EventOut:
    return EventOut(
        id=ev.id, correlation_id=ev.correlation_id, type=ev.type,
        token_code=ev.token.code if ev.token else None,
        counter_code=ev.counter.code if ev.counter else None,
        payload=ev.payload, created_at=ev.created_at,
    )


def list_events(db: Session, limit: int = 50, correlation_id: str | None = None) -> list[EventOut]:
    q = select(Event).order_by(Event.id.desc()).limit(limit)
    if correlation_id:
        q = select(Event).where(Event.correlation_id == correlation_id).order_by(Event.id.desc()).limit(limit)
    return [event_out(e) for e in reversed(db.scalars(q).all())]
