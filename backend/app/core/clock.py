"""Virtual clock: demo me "10 min aage badhao" possible, aur demo hamesha deterministic."""
from datetime import datetime, timedelta, timezone

_offset = timedelta(0)


def now() -> datetime:
    return datetime.now(timezone.utc) + _offset


def advance(minutes: float) -> datetime:
    global _offset
    _offset += timedelta(minutes=minutes)
    return now()


def reset() -> None:
    global _offset
    _offset = timedelta(0)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite timezone drop kar deta hai; read ke baad UTC wapas lagao."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
