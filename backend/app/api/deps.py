import uuid

from fastapi import Header


def correlation_id(x_correlation_id: str | None = Header(default=None)) -> str:
    """Member 1 chahe to X-Correlation-ID bhej ke apne events isi flow se jod sakta hai."""
    return x_correlation_id or str(uuid.uuid4())
