from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import clock
from app.db.base import Base
from app.models.counter import Counter
from app.models.enums import TokenStatus
from app.models.service import Service


def utcnow() -> datetime:
    return clock.now()


class Token(Base):
    """Ek patient ka queue token (Q101, Q102, ...)."""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # "Q101"
    patient_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)  # optional

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id"), nullable=True)

    status: Mapped[TokenStatus] = mapped_column(
        Enum(TokenStatus, values_callable=lambda e: [m.value for m in e]),
        default=TokenStatus.WAITING,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 0 normal, higher = urgent
    is_walk_in: Mapped[bool] = mapped_column(Boolean, default=False)

    # Optimistic locking: har update pe version badhta hai (double-click safety)
    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_change_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    service: Mapped[Service] = relationship()
    counter: Mapped[Counter | None] = relationship()

    __mapper_args__ = {"version_id_col": version}
