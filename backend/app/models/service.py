from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Service(Base):
    """Clinic ki service type: Blood Test, ECG, General Consultation."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # e.g. "blood_test"
    name: Mapped[str] = mapped_column(String(64))
    avg_duration_min: Mapped[float] = mapped_column(Float)  # baseline service time

    counter_links: Mapped[list["CounterService"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
