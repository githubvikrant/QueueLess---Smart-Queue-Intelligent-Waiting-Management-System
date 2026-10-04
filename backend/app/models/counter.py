from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Counter(Base):
    """Service counter (A, B, ...). Counter C kholna = is_open ko True karna."""

    __tablename__ = "counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)  # "A", "B"
    name: Mapped[str] = mapped_column(String(64))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    speed_factor: Mapped[float] = mapped_column(Float, default=1.0)  # <1 fast, >1 slow
    injected_delay_min: Mapped[float] = mapped_column(Float, default=0.0)  # demo delay

    service_links: Mapped[list["CounterService"]] = relationship(
        back_populates="counter", cascade="all, delete-orphan"
    )

    @property
    def service_codes(self) -> list[str]:
        return sorted(link.service.code for link in self.service_links)


class CounterService(Base):
    """Eligibility table: kaun sa counter kaun si service karta hai.
    Rule code me hard-coded nahi, data me hai, to naya counter = naye rows."""

    __tablename__ = "counter_services"

    counter_id: Mapped[int] = mapped_column(ForeignKey("counters.id"), primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)

    counter: Mapped[Counter] = relationship(back_populates="service_links")
    service: Mapped["Service"] = relationship(back_populates="counter_links")  # noqa: F821
