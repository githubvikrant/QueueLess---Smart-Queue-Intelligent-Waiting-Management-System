from app.core.errors import InvalidTransition
from app.models.enums import TokenStatus as S

# Token ki poori zindagi ek jagah. Isse bahar koi transition nahi hoga.
ALLOWED: dict[S, set[S]] = {
    S.WAITING: {S.CALLED, S.SKIPPED, S.NO_SHOW},
    S.CALLED: {S.IN_SERVICE, S.NO_SHOW, S.SKIPPED},
    S.IN_SERVICE: {S.COMPLETED},
    S.SKIPPED: {S.WAITING},
    S.NO_SHOW: {S.WAITING},
    S.COMPLETED: set(),
}

ACTIVE = {S.CALLED, S.IN_SERVICE}


def can_transition(current: S, target: S) -> bool:
    return target in ALLOWED[current]


def assert_transition(current: S, target: S) -> None:
    if not can_transition(current, target):
        allowed = ", ".join(sorted(s.value for s in ALLOWED[current])) or "none"
        raise InvalidTransition(
            f"Cannot move token from '{current.value}' to '{target.value}' (allowed: {allowed})"
        )
