import enum


class TokenStatus(str, enum.Enum):
    WAITING = "waiting"
    CALLED = "called"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    SKIPPED = "skipped"
