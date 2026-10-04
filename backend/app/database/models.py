"""
SQLAlchemy ORM models for QueueLess database.

This module defines all database tables used by the application:
- ServiceType: Service metadata with duration statistics
- Counter: Service counters with status and current token
- Token: Patient tokens with queue position and ETA data
- Recommendation: AI-generated action proposals with approval status
- AuditEntry: Complete audit trail of all events

PURPOSE: Define database schema using SQLAlchemy ORM
DEPENDENCIES: sqlalchemy, datetime, json
SIDE EFFECTS: Creates tables when init_db() is called
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.db import Base


class ServiceType(Base):
    """
    PURPOSE: Represents a type of medical service (e.g., Blood Test, ECG, Consultation)
    
    FIELDS:
        id: Primary key
        name: Service name (e.g., "Blood Test")
        avg_duration_min: Average service duration in minutes (rolling average)
        spread_min: Standard deviation of recent durations (for ETA uncertainty)
        recent_durations: JSON list of last 10 actual durations for rolling average
    
    RELATIONSHIPS:
        tokens: One-to-many relationship with Token records using this service
    
    USAGE: Used by eta_service to calculate expected duration and ETA uncertainty
    """
    __tablename__ = "service_types"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    avg_duration_min = Column(Float, nullable=False, default=0.0)
    spread_min = Column(Float, nullable=False, default=0.0)
    recent_durations = Column(JSON, nullable=False, default=list)
    
    # Relationship to tokens
    tokens = relationship("Token", back_populates="service_type")


class Counter(Base):
    """
    PURPOSE: Represents a service counter where patients are served
    
    FIELDS:
        id: Primary key (e.g., "A", "B")
        name: Display name (e.g., "Counter A")
        status: Current status (AVAILABLE, BUSY, CLOSED)
        supported_services: JSON list of service names this counter can handle
        current_token_id: Foreign key to Token currently being served (null if idle)
        expected_free_at: DateTime when counter will be available for next patient
    
    RELATIONSHIPS:
        current_token: Many-to-one relationship with Token (current patient)
        tokens: One-to-many relationship with Tokens assigned to this counter
    
    USAGE: Used by queue_engine for token assignment and eta_service for ETA calculation
    """
    __tablename__ = "counters"
    
    id = Column(String(10), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="AVAILABLE")
    supported_services = Column(JSON, nullable=False, default=list)
    current_token_id = Column(String(20), ForeignKey("tokens.id"), nullable=True)
    expected_free_at = Column(DateTime, nullable=True)
    
    # Relationships
    current_token = relationship("Token", foreign_keys=[current_token_id])
    tokens = relationship("Token", back_populates="assigned_counter", foreign_keys="Token.assigned_counter_id")


class Token(Base):
    """
    PURPOSE: Represents a patient token in the queue
    
    FIELDS:
        id: Primary key (e.g., "Q101", "Q102")
        service_id: Foreign key to ServiceType
        kind: Token type (WALK_IN or APPOINTMENT)
        appointment_time: Scheduled time for appointment tokens (null for walk-ins)
        priority_class: Integer priority (higher = more priority, staff-set only)
        status: Current state (WAITING, CALLED, IN_SERVICE, COMPLETED, NO_SHOW)
        assigned_counter_id: Foreign key to Counter assigned to this token
        created_at: When token was created
        called_at: When token was called to counter
        eta_low: Lower bound of ETA estimate (expected - K * spread)
        eta_expected: Expected ETA time
        eta_high: Upper bound of ETA estimate (expected + K * spread)
        eta_reason: Plain text explanation of why ETA is what it is
    
    RELATIONSHIPS:
        service_type: Many-to-one relationship with ServiceType
        assigned_counter: Many-to-one relationship with Counter
        recommendations: One-to-many relationship with Recommendations involving this token
    
    USAGE: Core entity for queue management, used by all services
    """
    __tablename__ = "tokens"
    
    id = Column(String(20), primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("service_types.id"), nullable=False)
    kind = Column(String(20), nullable=False, default="WALK_IN")
    appointment_time = Column(DateTime, nullable=True)
    priority_class = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="WAITING")
    assigned_counter_id = Column(String(10), ForeignKey("counters.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    called_at = Column(DateTime, nullable=True)
    eta_low = Column(DateTime, nullable=True)
    eta_expected = Column(DateTime, nullable=True)
    eta_high = Column(DateTime, nullable=True)
    eta_reason = Column(Text, nullable=True)
    
    # Relationships
    service_type = relationship("ServiceType", back_populates="tokens")
    assigned_counter = relationship("Counter", back_populates="tokens", foreign_keys=[assigned_counter_id])
    recommendations = relationship("Recommendation", back_populates="token")


class Recommendation(Base):
    """
    PURPOSE: Represents an AI-generated action proposal for queue optimization
    
    FIELDS:
        id: Primary key
        type: Action type (REASSIGN, OPEN_COUNTER, NOTIFY)
        token_id: Foreign key to Token this recommendation applies to
        from_counter_id: Source counter ID (for REASSIGN actions)
        to_counter_id: Target counter ID (for REASSIGN actions)
        wait_before_min: Calculated wait time before action (in minutes)
        wait_after_min: Calculated wait time after action (in minutes)
        reason: Plain text explanation from LLM
        status: Approval status (PENDING, APPROVED, REJECTED)
        created_at: When recommendation was generated
        decided_at: When recommendation was approved/rejected
    
    RELATIONSHIPS:
        token: Many-to-one relationship with Token
        audit_entries: One-to-many relationship with AuditEntries for this recommendation
    
    USAGE: Used by agent_service to propose actions and by api/agent for approval flow
    """
    __tablename__ = "recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(30), nullable=False)
    token_id = Column(String(20), ForeignKey("tokens.id"), nullable=True)
    from_counter_id = Column(String(10), nullable=True)
    to_counter_id = Column(String(10), nullable=True)
    wait_before_min = Column(Float, nullable=False)
    wait_after_min = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    
    # Relationships
    token = relationship("Token", back_populates="recommendations")
    audit_entries = relationship("AuditEntry", back_populates="recommendation")


class AuditEntry(Base):
    """
    PURPOSE: Complete audit trail of all events in the system
    
    FIELDS:
        id: Primary key
        timestamp: When the event occurred
        event_type: Type of event (BOTTLENECK_DETECTED, RECOMMENDATION, APPROVED, etc.)
        actor: Who initiated the event (SYSTEM, AGENT, RECEPTIONIST)
        input_data: JSON of input data for the event
        prediction: JSON of any predictions made
        recommendation_id: Foreign key to Recommendation if this is related to one
        decision: Decision made (text description)
        result: JSON of the result of the action
    
    RELATIONSHIPS:
        recommendation: Many-to-one relationship with Recommendation
    
    USAGE: Provides complete transparency for compliance and debugging
    """
    __tablename__ = "audit_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_type = Column(String(50), nullable=False)
    actor = Column(String(50), nullable=False)
    input_data = Column(JSON, nullable=True)
    prediction = Column(JSON, nullable=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=True)
    decision = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)
    
    # Relationships
    recommendation = relationship("Recommendation", back_populates="audit_entries")
