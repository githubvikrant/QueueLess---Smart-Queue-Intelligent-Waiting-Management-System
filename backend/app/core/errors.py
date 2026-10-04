class QueueError(Exception):
    status_code = 400
    code = "queue_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(QueueError):
    status_code, code = 404, "not_found"


class InvalidTransition(QueueError):
    status_code, code = 409, "invalid_transition"


class CounterUnavailable(QueueError):
    status_code, code = 409, "counter_unavailable"


class Conflict(QueueError):
    status_code, code = 409, "conflict"


class NotEligible(QueueError):
    status_code, code = 422, "not_eligible"


class NoCounterAvailable(QueueError):
    status_code, code = 422, "no_counter_available"
