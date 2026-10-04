"""Har change ke baad realtime events:
  queue:updated  - poora queue view
  eta:updated    - sirf wo tokens jinka ETA badla (dashboard inhe yellow karega)
  audit:new      - is flow ke naye audit events"""
from sqlalchemy.orm import Session

from app.realtime import broadcast
from app.services.presenter import build_queue_view, list_events

_last: dict[str, tuple] | None = None


def reset_tracking() -> None:
    global _last
    _last = None


async def publish_queue(db: Session, correlation_id: str, reason: str) -> None:
    global _last
    view = build_queue_view(db)
    current = {t.code: (t.eta_min, t.eta_max) for t in view.tokens}
    changed = []
    if _last is not None:
        changed = [c for c, v in current.items() if c in _last and _last[c] != v]
    _last = current

    await broadcast("queue:updated", {
        "correlation_id": correlation_id, "reason": reason, "queue": view.model_dump(mode="json"),
    })
    if changed:
        await broadcast("eta:updated", {
            "correlation_id": correlation_id, "reason": reason, "changed": changed,
            "tokens": [t.model_dump(mode="json") for t in view.tokens if t.code in changed],
        })
    events = list_events(db, limit=50, correlation_id=correlation_id)
    await broadcast("audit:new", {
        "correlation_id": correlation_id, "events": [e.model_dump(mode="json") for e in events],
    })
