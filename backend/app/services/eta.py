"""ETA hook. Abhi ek solid default algorithm hai taaki dashboard aaj hi chale.
Member 1 apna engine yahan plug karega:

    from app.services.eta import set_eta_provider
    set_eta_provider(my_eta_function)   # (QueueSnapshot) -> dict[str, EtaRange]
"""
from dataclasses import dataclass
from typing import Callable

from app.services.snapshot import CounterSnap, QueueSnapshot


@dataclass(frozen=True)
class EtaRange:
    eta_minutes: float  # point estimate
    eta_min: int  # range ka lower
    eta_max: int  # range ka upper
    position: int  # counter ki waiting line me position (0 = abhi serve ho raha)


def make_range(eta: float, position: int) -> EtaRange:
    lo = max(0, round(eta * 0.85))
    hi = max(lo + 1, round(eta * 1.25) + 1) if eta > 0 else 1
    return EtaRange(round(eta, 1), lo, hi, position)


ACTIVE = ("called", "in_service")


def _walk_counter(snap: QueueSnapshot, counter: CounterSnap) -> tuple[dict[str, EtaRange], float]:
    """Ek counter ki timeline. Returns (etas, minute jab naya token shuru hoga)."""
    etas: dict[str, EtaRange] = {}
    t = counter.injected_delay_min

    active = [x for x in snap.tokens if x.counter_code == counter.code and x.status in ACTIVE]
    if active:
        tok = active[0]
        dur = snap.service(tok.service_code).avg_duration_min * counter.speed_factor
        elapsed = 0.0
        if tok.status == "in_service" and tok.started_at:
            elapsed = max(0.0, (snap.now - tok.started_at).total_seconds() / 60)
        t = max(0.0, dur - elapsed) + counter.injected_delay_min
        etas[tok.code] = make_range(0, 0)

    waiting = sorted(
        (x for x in snap.tokens if x.counter_code == counter.code and x.status == "waiting"),
        key=lambda x: (-x.priority, x.created_at, x.code),
    )
    for i, tok in enumerate(waiting, start=1):
        etas[tok.code] = make_range(t, i)
        t += snap.service(tok.service_code).avg_duration_min * counter.speed_factor
    return etas, t


def default_eta_provider(snap: QueueSnapshot) -> dict[str, EtaRange]:
    out: dict[str, EtaRange] = {}
    for counter in snap.counters:
        if counter.is_open:
            out.update(_walk_counter(snap, counter)[0])
    return out


def projected_wait(snap: QueueSnapshot, counter_code: str) -> float:
    """Naya token is counter pe lagaya to kitne min baad shuru hoga."""
    return _walk_counter(snap, snap.counter(counter_code))[1]


EtaProvider = Callable[[QueueSnapshot], dict[str, EtaRange]]
_provider: EtaProvider = default_eta_provider


def set_eta_provider(fn: EtaProvider) -> None:
    global _provider
    _provider = fn


def reset_eta_provider() -> None:
    set_eta_provider(default_eta_provider)


def compute_etas(snap: QueueSnapshot) -> dict[str, EtaRange]:
    return _provider(snap)
