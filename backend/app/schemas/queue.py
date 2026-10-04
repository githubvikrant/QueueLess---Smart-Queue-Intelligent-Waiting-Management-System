"""
Pydantic schemas for request/response validation.

This module defines Pydantic models for validating API requests and responses.
These schemas ensure data integrity and provide automatic validation.

PURPOSE: Define request/response models for API endpoints
DEPENDENCIES: pydantic, datetime
SIDE EFFECTS: Provides validation for API endpoints
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


# ===== TOKEN SCHEMAS =====

class TokenBase(BaseModel):
    """
    PURPOSE: Base schema with common token fields
    
    FIELDS:
        service_id: ID of the service type
        kind: Token type (WALK_IN or APPOINTMENT)
        appointment_time: Optional scheduled time for appointments
        priority_class: Integer priority (higher = more priority)
    """
    service_id: int
    kind: str = Field(default="WALK_IN", pattern="^(WALK_IN|APPOINTMENT)$")
    appointment_time: Optional[datetime] = None
    priority_class: int = Field(default=0, ge=0)


class TokenCreate(TokenBase):
    """
    PURPOSE: Schema for creating a new token (check-in)
    
    INHERITS: All fields from TokenBase
    USAGE: Used in POST /api/queue/checkin endpoint
    """
    pass


class TokenResponse(BaseModel):
    """
    PURPOSE: Schema for token response (read-only)
    
    FIELDS:
        id: Token ID (e.g., "Q101")
        service_id: ID of the service type
        service_name: Name of the service (from ServiceType)
        kind: Token type
        appointment_time: Scheduled time (if appointment)
        priority_class: Priority level
        status: Current state
        assigned_counter_id: Counter ID if assigned
        assigned_counter_name: Counter name if assigned
        created_at: When token was created
        called_at: When token was called
        eta_low: Lower bound of ETA estimate
        eta_expected: Expected ETA time
        eta_high: Upper bound of ETA estimate
        eta_reason: Explanation of ETA
    
    USAGE: Returned by GET /api/queue/ and GET /api/queue/{token_id}
    """
    id: str
    service_id: int
    service_name: Optional[str] = None
    kind: str
    appointment_time: Optional[datetime] = None
    priority_class: int
    status: str
    assigned_counter_id: Optional[str] = None
    assigned_counter_name: Optional[str] = None
    created_at: datetime
    called_at: Optional[datetime] = None
    eta_low: Optional[datetime] = None
    eta_expected: Optional[datetime] = None
    eta_high: Optional[datetime] = None
    eta_reason: Optional[str] = None
    
    class Config:
        """
        Pydantic configuration to allow ORM mode
        """
        from_attributes = True


# ===== COUNTER SCHEMAS =====

class CounterBase(BaseModel):
    """
    PURPOSE: Base schema with common counter fields
    
    FIELDS:
        name: Display name
        status: Current status (AVAILABLE, BUSY, CLOSED)
        supported_services: List of service names this counter can handle
    """
    name: str
    status: str = Field(default="AVAILABLE", pattern="^(AVAILABLE|BUSY|CLOSED)$")
    supported_services: List[str] = Field(default_factory=list)


class CounterUpdate(BaseModel):
    """
    PURPOSE: Schema for updating counter status
    
    FIELDS:
        status: New status to set
    
    USAGE: Used in POST /api/counters/{id}/status endpoint
    """
    status: str = Field(pattern="^(AVAILABLE|BUSY|CLOSED)$")


class CounterResponse(BaseModel):
    """
    PURPOSE: Schema for counter response (read-only)
    
    FIELDS:
        id: Counter ID (e.g., "A", "B")
        name: Display name
        status: Current status
        supported_services: List of supported service names
        current_token_id: ID of token currently being served
        current_token: Current token details if any
        expected_free_at: When counter will be available
    
    USAGE: Returned by GET /api/counters/
    """
    id: str
    name: str
    status: str
    supported_services: List[str]
    current_token_id: Optional[str] = None
    current_token: Optional[TokenResponse] = None
    expected_free_at: Optional[datetime] = None
    
    class Config:
        """
        Pydantic configuration to allow ORM mode
        """
        from_attributes = True


# ===== RECOMMENDATION SCHEMAS =====

class RecommendationBase(BaseModel):
    """
    PURPOSE: Base schema with common recommendation fields
    
    FIELDS:
        type: Action type (REASSIGN, OPEN_COUNTER, NOTIFY)
        token_id: Token this recommendation applies to
        from_counter_id: Source counter (for REASSIGN)
        to_counter_id: Target counter (for REASSIGN)
        wait_before_min: Wait time before action
        wait_after_min: Wait time after action
        reason: Explanation from LLM
    """
    type: str = Field(pattern="^(REASSIGN|OPEN_COUNTER|NOTIFY)$")
    token_id: Optional[str] = None
    from_counter_id: Optional[str] = None
    to_counter_id: Optional[str] = None
    wait_before_min: float
    wait_after_min: float
    reason: str


class RecommendationResponse(BaseModel):
    """
    PURPOSE: Schema for recommendation response (read-only)
    
    FIELDS:
        id: Recommendation ID
        type: Action type
        token_id: Token ID
        token: Token details if applicable
        from_counter_id: Source counter
        to_counter_id: Target counter
        wait_before_min: Wait time before
        wait_after_min: Wait time after
        reason: Explanation
        status: Approval status (PENDING, APPROVED, REJECTED)
        created_at: When created
        decided_at: When decided
    
    USAGE: Returned by GET /api/agent/recommendations
    """
    id: int
    type: str
    token_id: Optional[str] = None
    token: Optional[TokenResponse] = None
    from_counter_id: Optional[str] = None
    to_counter_id: Optional[str] = None
    wait_before_min: float
    wait_after_min: float
    reason: str
    status: str = Field(pattern="^(PENDING|APPROVED|REJECTED)$")
    created_at: datetime
    decided_at: Optional[datetime] = None
    
    class Config:
        """
        Pydantic configuration to allow ORM mode
        """
        from_attributes = True


# ===== AUDIT ENTRY SCHEMAS =====

class AuditEntryResponse(BaseModel):
    """
    PURPOSE: Schema for audit entry response (read-only)
    
    FIELDS:
        id: Entry ID
        timestamp: When event occurred
        event_type: Type of event
        actor: Who initiated (SYSTEM, AGENT, RECEPTIONIST)
        input_data: Input data as JSON
        prediction: Predictions as JSON
        recommendation_id: Related recommendation ID
        decision: Decision made
        result: Result as JSON
    
    USAGE: Returned by GET /api/notifications/audit
    """
    id: int
    timestamp: datetime
    event_type: str
    actor: str
    input_data: Optional[Dict[str, Any]] = None
    prediction: Optional[Dict[str, Any]] = None
    recommendation_id: Optional[int] = None
    decision: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    class Config:
        """
        Pydantic configuration to allow ORM mode
        """
        from_attributes = True


# ===== SIMULATION SCHEMAS =====

class SimulationRequest(BaseModel):
    """
    PURPOSE: Schema for simulation request
    
    FIELDS:
        extra_patients: Number of additional patients to simulate
        extra_counters: Number of additional counters to simulate
        service_delay_min: Additional delay to add to all services
    
    USAGE: Used in POST /api/simulation/ endpoint
    """
    extra_patients: int = Field(default=0, ge=0)
    extra_counters: int = Field(default=0, ge=0)
    service_delay_min: int = Field(default=0, ge=0)


class SimulationResponse(BaseModel):
    """
    PURPOSE: Schema for simulation response
    
    FIELDS:
        current: Current state metrics
        proposed: Proposed state metrics
        difference: Difference between current and proposed
        is_simulation: Always True (Non-Negotiable Rule #8)
    
    USAGE: Returned by POST /api/simulation/
    """
    current: Dict[str, Any]
    proposed: Dict[str, Any]
    difference: Dict[str, Any]
    is_simulation: bool = Field(default=True, description="Always True for simulations")


# ===== AGENT CHAT SCHEMAS =====

class AgentChatRequest(BaseModel):
    """
    PURPOSE: Schema for agent chat request
    
    FIELDS:
        message: Natural language message to send to LLM agent
    
    USAGE: Used in POST /api/agent/chat endpoint
    """
    message: str


class AgentChatResponse(BaseModel):
    """
    PURPOSE: Schema for agent chat response
    
    FIELDS:
        response: Agent's natural language response
        recommendations: Any recommendations created by the agent
    
    USAGE: Returned by POST /api/agent/chat
    """
    response: str
    recommendations: Optional[List[RecommendationResponse]] = None


# ===== DEMO CONTROL SCHEMAS =====

class InjectDelayRequest(BaseModel):
    """
    PURPOSE: Schema for injecting delay into a counter (demo control)
    
    FIELDS:
        counter_id: Counter to inject delay into
        extra_minutes: Number of minutes to add
    
    USAGE: Used in POST /api/queue/demo/inject-delay
    """
    counter_id: str
    extra_minutes: int = Field(gt=0)


class AddWalkinsRequest(BaseModel):
    """
    PURPOSE: Schema for adding walk-in patients (demo control)
    
    FIELDS:
        count: Number of walk-in patients to add
    
    USAGE: Used in POST /api/queue/demo/add-walkins
    """
    count: int = Field(gt=0)


class MarkNoshowRequest(BaseModel):
    """
    PURPOSE: Schema for marking a token as no-show (demo control)
    
    FIELDS:
        token_id: Token to mark as no-show
    
    USAGE: Used in POST /api/queue/demo/mark-noshow
    """
    token_id: str
