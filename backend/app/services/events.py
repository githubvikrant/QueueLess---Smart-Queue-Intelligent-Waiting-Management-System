from sqlalchemy.orm import Session

from app.models import Counter, Event, Token


def log_event(
    db: Session,
    type: str,
    correlation_id: str,
    token: Token | None = None,
    counter: Counter | None = None,
    payload: dict | None = None,
) -> Event:
    ev = Event(
        correlation_id=correlation_id,
        type=type,
        token_id=token.id if token else None,
        counter_id=counter.id if counter else None,
        payload=payload or {},
    )
    db.add(ev)
    return ev
