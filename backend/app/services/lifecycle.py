"""Token lifecycle + counter operations. Har function ek transaction hai
(data change + audit event ek saath commit)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import (
    Conflict, CounterUnavailable, NoCounterAvailable, NotEligible, NotFound,
)
from app.models import Counter, CounterService, Service, Token, TokenStatus as S
from app.services import state_machine
from app.services.eta import projected_wait
from app.services.events import log_event
from app.services.snapshot import QueueSnapshot, build_snapshot


# ---------- lookups ----------
def get_token(db: Session, code: str) -> Token:
    t = db.scalar(select(Token).where(Token.code == code.upper()))
    if not t:
        raise NotFound(f"Token {code} not found")
    return t


def get_counter(db: Session, code: str) -> Counter:
    c = db.scalar(select(Counter).where(Counter.code == code.upper()))
    if not c:
        raise NotFound(f"Counter {code} not found")
    return c


def get_service(db: Session, code: str) -> Service:
    s = db.scalar(select(Service).where(Service.code == code))
    if not s:
        raise NotFound(f"Service '{code}' not found")
    return s


# ---------- routing ----------
def pick_counter(snap: QueueSnapshot, service_code: str) -> str | None:
    """Eligible + open counters me se jahan sabse kam wait ho."""
    candidates = [c for c in snap.counters if c.is_open and service_code in c.service_codes]
    if not candidates:
        return None
    return min(candidates, key=lambda c: (projected_wait(snap, c.code), c.code)).code


def _next_code(db: Session) -> str:
    nums = [int(c[1:]) for c in db.scalars(select(Token.code)).all() if c[1:].isdigit()]
    return f"Q{max(nums, default=100) + 1}"


# ---------- join ----------
def create_token(
    db: Session, corr: str, patient_name: str, service_code: str,
    phone: str | None = None, priority: int = 0, is_walk_in: bool = False,
) -> Token:
    service = get_service(db, service_code)
    counter_code = pick_counter(build_snapshot(db), service.code)
    if counter_code is None:
        raise NoCounterAvailable(f"No open counter offers {service.name}")
    counter = get_counter(db, counter_code)
    token = Token(
        code=_next_code(db), patient_name=patient_name.strip(), phone=phone,
        service_id=service.id, counter_id=counter.id, priority=priority,
        is_walk_in=is_walk_in, status=S.WAITING,
    )
    db.add(token)
    db.flush()
    log_event(db, "token.joined", corr, token, counter, {
        "token_code": token.code, "service": service.code, "counter": counter.code,
        "priority": priority, "walk_in": is_walk_in,
    })
    return token


def join_token(db: Session, corr: str, **kw) -> Token:
    token = create_token(db, corr, **kw)
    db.commit()
    return token


# ---------- lifecycle ----------
def _require_open_counter(token: Token) -> Counter:
    if token.counter is None:
        raise NoCounterAvailable(f"Token {token.code} has no counter assigned")
    if not token.counter.is_open:
        raise CounterUnavailable(f"Counter {token.counter.code} is closed")
    return token.counter


def call_token(db: Session, code: str, corr: str) -> Token:
    token = get_token(db, code)
    state_machine.assert_transition(token.status, S.CALLED)
    counter = _require_open_counter(token)
    busy = db.scalar(select(Token).where(
        Token.counter_id == counter.id, Token.status.in_(state_machine.ACTIVE), Token.id != token.id,
    ))
    if busy:
        raise CounterUnavailable(f"Counter {counter.code} is busy with {busy.code}")
    token.status = S.CALLED
    token.called_at = clock.now()
    token.last_change_reason = None
    log_event(db, "token.called", corr, token, counter, {"token_code": token.code, "counter": counter.code})
    db.commit()
    return token


def call_next(db: Session, counter_code: str, corr: str) -> Token:
    counter = get_counter(db, counter_code)
    waiting = db.scalars(select(Token).where(
        Token.counter_id == counter.id, Token.status == S.WAITING,
    )).all()
    if not waiting:
        raise NotFound(f"No waiting tokens on Counter {counter.code}")
    head = min(waiting, key=lambda t: (-t.priority, clock.as_utc(t.created_at), t.code))
    return call_token(db, head.code, corr)


def start_service(db: Session, code: str, corr: str) -> Token:
    token = get_token(db, code)
    state_machine.assert_transition(token.status, S.IN_SERVICE)
    token.status = S.IN_SERVICE
    token.started_at = clock.now()
    log_event(db, "token.service_started", corr, token, token.counter,
              {"token_code": token.code, "counter": token.counter.code if token.counter else None})
    db.commit()
    return token


def complete_service(db: Session, code: str, corr: str) -> Token:
    token = get_token(db, code)
    state_machine.assert_transition(token.status, S.COMPLETED)
    now = clock.now()
    token.status = S.COMPLETED
    token.completed_at = now
    started = clock.as_utc(token.started_at)
    token.actual_duration_min = round((now - started).total_seconds() / 60, 2) if started else None
    if token.counter:
        token.counter.injected_delay_min = 0.0  # delay us service ka tha jo ab khatam
    log_event(db, "token.completed", corr, token, token.counter, {
        "token_code": token.code, "actual_duration_min": token.actual_duration_min,
    })
    db.commit()
    return token


def _simple_transition(db: Session, code: str, corr: str, target: S, event: str) -> Token:
    token = get_token(db, code)
    state_machine.assert_transition(token.status, target)
    token.status = target
    if target == S.WAITING:
        token.called_at = None
    log_event(db, event, corr, token, token.counter, {"token_code": token.code, "to": target.value})
    db.commit()
    return token


def mark_no_show(db, code, corr):
    return _simple_transition(db, code, corr, S.NO_SHOW, "token.no_show")


def skip_token(db, code, corr):
    return _simple_transition(db, code, corr, S.SKIPPED, "token.skipped")


def recall_token(db, code, corr):
    return _simple_transition(db, code, corr, S.WAITING, "token.recalled")


# ---------- reassign (Member 1 ka Approve yahi call karega) ----------
def reassign_token(db: Session, code: str, counter_code: str, corr: str, reason: str | None = None) -> Token:
    token = get_token(db, code)
    if token.status != S.WAITING:
        raise Conflict(f"Only waiting tokens can be reassigned (token is '{token.status.value}')")
    target = get_counter(db, counter_code)
    if not target.is_open:
        raise CounterUnavailable(f"Counter {target.code} is closed")
    if token.service.code not in target.service_codes:
        raise NotEligible(f"Counter {target.code} does not offer {token.service.name}")
    if token.counter_id == target.id:
        raise Conflict(f"{token.code} is already on Counter {target.code}")
    old = token.counter.code if token.counter else None
    token.counter = target
    token.last_change_reason = reason or f"Moved from Counter {old} to Counter {target.code}"
    log_event(db, "token.reassigned", corr, token, target, {
        "token_code": token.code, "from": old, "to": target.code, "reason": token.last_change_reason,
    })
    db.commit()
    return token


# ---------- counters ----------
def inject_delay(db: Session, counter_code: str, minutes: float, corr: str) -> Counter:
    counter = get_counter(db, counter_code)
    counter.injected_delay_min += minutes
    for t in db.scalars(select(Token).where(Token.counter_id == counter.id, Token.status == S.WAITING)):
        t.last_change_reason = f"Counter {counter.code} is running {minutes:g} min behind"
    log_event(db, "counter.delay_injected", corr, None, counter, {
        "counter": counter.code, "minutes": minutes, "total_delay_min": counter.injected_delay_min,
    })
    db.commit()
    return counter


def create_counter(db: Session, code: str, name: str, service_codes: list[str],
                   is_open: bool, speed_factor: float, corr: str) -> Counter:
    code = code.upper()
    if db.scalar(select(Counter).where(Counter.code == code)):
        raise Conflict(f"Counter {code} already exists")
    services = [get_service(db, s) for s in service_codes]
    counter = Counter(code=code, name=name, is_open=is_open, speed_factor=speed_factor)
    db.add(counter)
    db.flush()
    db.add_all(CounterService(counter_id=counter.id, service_id=s.id) for s in services)
    log_event(db, "counter.created", corr, None, counter, {"counter": code, "services": service_codes})
    db.commit()
    return counter


def close_counter(db: Session, code: str, corr: str) -> Counter:
    counter = get_counter(db, code)
    if not counter.is_open:
        return counter
    counter.is_open = False
    db.flush()
    waiting = db.scalars(select(Token).where(
        Token.counter_id == counter.id, Token.status == S.WAITING).order_by(Token.id)).all()
    moved = unplaced = 0
    for t in waiting:
        new_code = pick_counter(build_snapshot(db), t.service.code)
        t.counter = get_counter(db, new_code) if new_code else None
        t.last_change_reason = (
            f"Counter {counter.code} closed; moved to Counter {new_code}" if new_code
            else f"Counter {counter.code} closed; waiting for a counter"
        )
        moved += bool(new_code)
        unplaced += not new_code
        db.flush()
        log_event(db, "token.reassigned", corr, t, None, {
            "token_code": t.code, "from": counter.code, "to": new_code, "reason": "counter_closed",
        })
    log_event(db, "counter.closed", corr, None, counter,
              {"counter": counter.code, "moved": moved, "unplaced": unplaced})
    db.commit()
    return counter


def open_counter(db: Session, code: str, corr: str) -> Counter:
    counter = get_counter(db, code)
    if counter.is_open:
        return counter
    counter.is_open = True
    db.flush()
    placed = 0
    for t in db.scalars(select(Token).where(Token.counter_id.is_(None), Token.status == S.WAITING)):
        new_code = pick_counter(build_snapshot(db), t.service.code)
        if new_code:
            t.counter = get_counter(db, new_code)
            t.last_change_reason = f"Assigned to Counter {new_code}"
            placed += 1
            db.flush()
    log_event(db, "counter.opened", corr, None, counter, {"counter": counter.code, "placed": placed})
    db.commit()
    return counter


# ---------- one-click advance (prototype) ----------
def advance_counter(db: Session, counter_code: str, corr: str) -> None:
    """
    One-click flow for prototype: minimal human interference.
    1. Complete whoever is currently called/in_service on this counter.
    2. Call the next waiting patient.
    3. Immediately start their service (skip the 'called' limbo).
    """
    counter = get_counter(db, counter_code)

    # Step 1: complete/dismiss the active token (called or in_service)
    active = db.scalar(select(Token).where(
        Token.counter_id == counter.id,
        Token.status.in_(state_machine.ACTIVE),
    ))
    if active:
        now = clock.now()
        active.status = S.COMPLETED
        active.completed_at = now
        started = clock.as_utc(active.started_at)
        active.actual_duration_min = round((now - started).total_seconds() / 60, 2) if started else None
        counter.injected_delay_min = 0.0
        log_event(db, "token.completed", corr, active, counter, {
            "token_code": active.code, "actual_duration_min": active.actual_duration_min,
        })
        db.flush()

    # Step 2: find next waiting patient on this counter
    waiting = db.scalars(select(Token).where(
        Token.counter_id == counter.id,
        Token.status == S.WAITING,
    )).all()
    if not waiting:
        db.commit()
        return

    next_token = min(waiting, key=lambda t: (-t.priority, clock.as_utc(t.created_at), t.code))

    # Step 3: call + immediately start (skip manual 'called' step)
    now = clock.now()
    next_token.status = S.IN_SERVICE
    next_token.called_at = now
    next_token.started_at = now
    next_token.last_change_reason = None
    log_event(db, "token.called", corr, next_token, counter, {
        "token_code": next_token.code, "counter": counter.code,
    })
    log_event(db, "token.service_started", corr, next_token, counter, {
        "token_code": next_token.code, "counter": counter.code,
    })
    db.commit()
