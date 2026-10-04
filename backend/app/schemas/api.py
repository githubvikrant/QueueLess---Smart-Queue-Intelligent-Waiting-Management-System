from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------- requests ----------
class JoinRequest(BaseModel):
    patient_name: str = Field(min_length=1, max_length=120)
    service_code: str
    phone: str | None = Field(default=None, max_length=20)
    priority: int = Field(default=0, ge=0, le=5)
    is_walk_in: bool = False


class ReassignRequest(BaseModel):
    counter_code: str
    reason: str | None = Field(default=None, max_length=255)


class DelayRequest(BaseModel):
    counter_code: str
    minutes: float = Field(gt=0, le=120)


class WalkInRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)


class AdvanceClockRequest(BaseModel):
    minutes: float = Field(gt=0, le=240)


class CounterCreate(BaseModel):
    code: str = Field(min_length=1, max_length=8)
    name: str = Field(min_length=1, max_length=64)
    services: list[str] = Field(min_length=1)
    is_open: bool = False
    speed_factor: float = Field(default=1.0, gt=0, le=5)


# ---------- responses ----------
class TokenOut(BaseModel):
    code: str
    patient_name: str
    service_code: str
    service_name: str
    counter_code: str | None
    status: str
    priority: int
    is_walk_in: bool
    position: int | None  # counter ki waiting line me; 0 = abhi serve ho raha
    eta_minutes: float | None
    eta_min: int | None
    eta_max: int | None
    eta_text: str  # patient-friendly: "about 8-12 minutes"
    last_change_reason: str | None
    created_at: datetime
    called_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None


class CounterOut(BaseModel):
    code: str
    name: str
    is_open: bool
    speed_factor: float
    injected_delay_min: float
    service_codes: list[str]
    current_token: str | None
    waiting_count: int
    projected_wait_min: float


class QueueStats(BaseModel):
    total: int
    waiting: int
    called: int
    in_service: int
    completed: int
    no_show: int
    skipped: int


class QueueOut(BaseModel):
    now: datetime
    counters: list[CounterOut]
    tokens: list[TokenOut]
    stats: QueueStats


class EventOut(BaseModel):
    id: int
    correlation_id: str
    type: str
    token_code: str | None
    counter_code: str | None
    payload: dict[str, Any]
    created_at: datetime
