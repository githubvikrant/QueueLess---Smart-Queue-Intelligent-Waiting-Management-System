from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.counter import Counter
from app.models.token import Token, utcnow


class Event(Base):
    """Append-only audit log. Delay -> ETA -> recommendation -> approve ki poori timeline."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)  # ek flow ke events ek id
    type: Mapped[str] = mapped_column(String(64), index=True)  # "token.called", "delay.injected"
    token_id: Mapped[int | None] = mapped_column(ForeignKey("tokens.id"), nullable=True)
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    token: Mapped[Token | None] = relationship()
    counter: Mapped[Counter | None] = relationship()
