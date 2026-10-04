from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core import clock
from app.models import Counter, CounterService, Event, Service, Token, TokenStatus
from app.seeding.data import COUNTERS, SERVICES, TOKENS


def reseed(db: Session) -> dict:
    """Sab kuch saaf karke CityCare demo state load karta hai. Clock bhi reset."""
    for model in (Event, Token, CounterService, Counter, Service):
        db.execute(delete(model))
    db.commit()
    clock.reset()
    now = clock.now()

    services = {c: Service(code=c, name=n, avg_duration_min=m) for c, n, m in SERVICES}
    counters = {c: Counter(code=c, name=n) for c, n, _ in COUNTERS}
    db.add_all([*services.values(), *counters.values()])
    db.flush()
    for code, _, svc_codes in COUNTERS:
        db.add_all(CounterService(counter_id=counters[code].id, service_id=services[s].id) for s in svc_codes)

    total = len(TOKENS)
    for i, (code, name, svc, counter, status, prio) in enumerate(TOKENS):
        st = TokenStatus(status)
        db.add(Token(
            code=code, patient_name=name, service_id=services[svc].id,
            counter_id=counters[counter].id, status=st, priority=prio,
            created_at=now - timedelta(minutes=total - i),
            called_at=now if st != TokenStatus.WAITING else None,
            started_at=now if st == TokenStatus.IN_SERVICE else None,
        ))
    db.commit()
    return {"services": len(SERVICES), "counters": len(COUNTERS), "tokens": total}


def ensure_seeded(db: Session) -> None:
    if db.query(Service).count() == 0:
        reseed(db)
