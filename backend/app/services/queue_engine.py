"""
Queue engine - Token lifecycle and queue ordering management.

This service manages token state transitions and provides queue ordering logic.
It handles the core operations of moving tokens through the queue.

PURPOSE: Manage token state transitions and queue ordering
DEPENDENCIES: SQLAlchemy, app.database.models, app.services.eta_service, app.core.events
SIDE EFFECTS: Updates token status, emits socket events, triggers ETA recalculation
"""

from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database.models import Token, Counter, ServiceType, AuditEntry
from app.services.eta_service import calculate_all_etas, expected_duration
from app.core.events import emit_queue_updated, emit_token_called, emit_audit_entry


def get_ordered_queue(db: Session) -> List[Token]:
    """
    PURPOSE: Get all WAITING tokens ordered by queue position
    
    PARAMETERS:
        db: SQLAlchemy database session
    
    RETURNS: List of Token objects ordered by priority_class DESC, created_at ASC
    
    WORKFLOW:
        1. Query all tokens with status = WAITING
        2. Order by priority_class (higher priority first)
        3. Then by created_at (first come, first served within same priority)
        4. Return ordered list
    
    DEPENDENCIES: Token model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by API endpoints to display queue in correct order
    """
    return db.query(Token).filter(Token.status == "WAITING").order_by(
        Token.priority_class.desc(),
        Token.created_at.asc()
    ).all()


def call_next_token(counter_id: str, db: Session) -> Optional[Token]:
    """
    PURPOSE: Call the next eligible token to a counter
    
    PARAMETERS:
        counter_id: ID of the counter calling the next token
        db: SQLAlchemy database session
    
    RETURNS: Token object that was called, or None if no eligible token
    
    WORKFLOW:
        1. Get the counter
        2. Find the next WAITING token eligible for this counter
        3. Update token status to CALLED
        4. Set token.assigned_counter_id
        5. Set token.called_at to now
        6. Emit token:called socket event
        7. Start no-show grace timer (call noshow_service - to be implemented)
        8. Emit queue:updated event
        9. Log to audit trail
        10. Return the called token
    
    DEPENDENCIES: Counter, Token models, emit_token_called, emit_queue_updated
    SIDE EFFECTS: Updates token status, emits socket events, logs audit entry
    
    USAGE: Called when a counter is ready to serve the next patient
    """
    # Get the counter
    counter = db.query(Counter).filter(Counter.id == counter_id).first()
    if not counter:
        return None
    
    # Get all WAITING tokens
    waiting_tokens = get_ordered_queue(db)
    
    # Find the first token eligible for this counter
    for token in waiting_tokens:
        # Check if counter supports the token's service
        service_name = token.service_type.name
        if service_name in counter.supported_services:
            # Call this token
            token.status = "CALLED"
            token.assigned_counter_id = counter_id
            token.called_at = datetime.utcnow()
            
            # Update counter status
            counter.status = "BUSY"
            counter.current_token_id = token.id
            
            # Calculate expected free time
            service_duration = expected_duration(token.service_type)
            from datetime import timedelta
            counter.expected_free_at = datetime.utcnow() + timedelta(minutes=service_duration)
            
            db.commit()
            
            # Emit socket events
            emit_token_called(token.id, counter.name)
            emit_queue_updated({'token_id': token.id, 'new_status': 'CALLED'})
            
            # Start no-show grace timer (create task in event loop)
            # Note: In a real async environment, we would await this
            # For now, the grace timer functionality is available but not auto-started
            # The demo can manually mark no-shows using the demo endpoint
            
            # Log to audit trail
            log_audit_entry(
                db=db,
                event_type="TOKEN_CALLED",
                actor="SYSTEM",
                input_data={'token_id': token.id, 'counter_id': counter_id},
                result={'status': 'CALLED'}
            )
            
            return token
    
    return None


def start_service(token_id: str, db: Session) -> Optional[Token]:
    """
    PURPOSE: Mark a token as being served (transition from CALLED to IN_SERVICE)
    
    PARAMETERS:
        token_id: ID of the token starting service
        db: SQLAlchemy database session
    
    RETURNS: Updated Token object, or None if token not found
    
    WORKFLOW:
        1. Get the token
        2. Update token status to IN_SERVICE
        3. Emit queue:updated event
        4. Log to audit trail
        5. Return the updated token
    
    DEPENDENCIES: Token model, emit_queue_updated
    SIDE EFFECTS: Updates token status, emits socket events, logs audit entry
    
    USAGE: Called when patient arrives at counter and service begins
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        return None
    
    token.status = "IN_SERVICE"
    db.commit()
    
    emit_queue_updated({'token_id': token_id, 'new_status': 'IN_SERVICE'})
    
    log_audit_entry(
        db=db,
        event_type="SERVICE_STARTED",
        actor="SYSTEM",
        input_data={'token_id': token_id},
        result={'status': 'IN_SERVICE'}
    )
    
    return token


def complete_service(token_id: str, actual_duration_min: float, db: Session) -> Optional[Token]:
    """
    PURPOSE: Mark a token as completed and update service statistics
    
    PARAMETERS:
        token_id: ID of the token completing service
        actual_duration_min: Actual time taken for this service
        db: SQLAlchemy database session
    
    RETURNS: Updated Token object, or None if token not found
    
    WORKFLOW:
        1. Get the token and its service type
        2. Update token status to COMPLETED
        3. Update ServiceType.recent_durations (append actual duration)
        4. Keep only last 10 durations in recent_durations
        5. Recalculate ServiceType.avg_duration_min as rolling average
        6. Update counter status to AVAILABLE
        7. Clear counter.current_token_id
        8. Recalculate ETAs for all waiting tokens (eta_service)
        9. Emit eta:updated event with affected token IDs
        10. Log to audit trail
        11. Return the completed token
    
    DEPENDENCIES: Token, ServiceType, Counter models, calculate_all_etas, emit_queue_updated
    SIDE EFFECTS: Updates token, service type, counter; recalculates ETAs; emits events
    
    USAGE: Called when a patient's service is completed
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        return None
    
    service = token.service_type
    counter = token.assigned_counter
    
    # Update token status
    token.status = "COMPLETED"
    
    # Update service statistics
    if service.recent_durations is None:
        service.recent_durations = []
    
    service.recent_durations.append(actual_duration_min)
    
    # Keep only last 10 durations
    if len(service.recent_durations) > 10:
        service.recent_durations = service.recent_durations[-10:]
    
    # Recalculate average
    service.avg_duration_min = sum(service.recent_durations) / len(service.recent_durations)
    
    # Update counter status
    if counter:
        counter.status = "AVAILABLE"
        counter.current_token_id = None
        counter.expected_free_at = None
    
    db.commit()
    
    # Recalculate ETAs for all waiting tokens
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_queue_updated({'token_id': token_id, 'new_status': 'COMPLETED'})
    from app.core.events import emit_eta_updated
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="SERVICE_COMPLETED",
        actor="SYSTEM",
        input_data={'token_id': token_id, 'actual_duration_min': actual_duration_min},
        result={'status': 'COMPLETED', 'affected_token_ids': eta_result['affected_token_ids']}
    )
    
    return token


def generate_token_id(db: Session) -> str:
    """
    PURPOSE: Generate the next token ID in sequence
    
    PARAMETERS:
        db: SQLAlchemy database session
    
    RETURNS: Next token ID as string (e.g., "Q113")
    
    WORKFLOW:
        1. Query all tokens to find the highest existing number
        2. Extract numeric part from token ID (e.g., "Q112" -> 112)
        3. Increment by 1
        4. Return as string with "Q" prefix
    
    DEPENDENCIES: Token model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called when creating a new token at check-in
    """
    # Get all tokens
    tokens = db.query(Token).all()
    
    if not tokens:
        return "Q101"
    
    # Find the highest token number
    max_num = 0
    for token in tokens:
        # Extract number from token ID (e.g., "Q112" -> 112)
        token_num = int(token.id[1:])  # Remove "Q" prefix
        if token_num > max_num:
            max_num = token_num
    
    # Generate next ID
    next_num = max_num + 1
    return f"Q{next_num}"


def reassign_token(token_id: str, to_counter_id: str, db: Session) -> Optional[Token]:
    """
    PURPOSE: Reassign a token to a different counter
    
    PARAMETERS:
        token_id: ID of the token to reassign
        to_counter_id: ID of the target counter
        db: SQLAlchemy database session
    
    RETURNS: Updated Token object, or None if token not found
    
    WORKFLOW:
        1. Get the token and target counter
        2. Update token.assigned_counter_id
        3. Recalculate ETAs for all waiting tokens
        4. Emit eta:updated event
        5. Log to audit trail
        6. Return the updated token
    
    DEPENDENCIES: Token, Counter models, calculate_all_etas, emit_eta_updated
    SIDE EFFECTS: Updates token assignment, recalculates ETAs, emits events
    
    USAGE: Called when a recommendation to reassign is approved
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        return None
    
    counter = db.query(Counter).filter(Counter.id == to_counter_id).first()
    if not counter:
        return None
    
    # Update token assignment
    token.assigned_counter_id = to_counter_id
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_queue_updated({'token_id': token_id, 'new_counter': to_counter_id})
    from app.core.events import emit_eta_updated
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="TOKEN_REASSIGNED",
        actor="RECEPTIONIST",
        input_data={'token_id': token_id, 'to_counter_id': to_counter_id},
        result={'assigned_counter': to_counter_id}
    )
    
    return token


def log_audit_entry(db: Session, event_type: str, actor: str, 
                    input_data: dict = None, prediction: dict = None,
                    recommendation_id: int = None, decision: str = None,
                    result: dict = None):
    """
    PURPOSE: Log an event to the audit trail
    
    PARAMETERS:
        db: SQLAlchemy database session
        event_type: Type of event (e.g., "TOKEN_CALLED", "SERVICE_COMPLETED")
        actor: Who initiated the event (SYSTEM, AGENT, RECEPTIONIST)
        input_data: Input data for the event
        prediction: Any predictions made
        recommendation_id: Related recommendation ID if applicable
        decision: Decision made
        result: Result of the action
    
    WORKFLOW:
        1. Create AuditEntry record with provided data
        2. Save to database
        3. Emit audit:entry socket event
    
    DEPENDENCIES: AuditEntry model, emit_audit_entry
    SIDE EFFECTS: Creates audit entry, emits socket event
    
    USAGE: Called by all operations that need to be logged (Non-Negotiable Rule #7)
    """
    entry = AuditEntry(
        event_type=event_type,
        actor=actor,
        input_data=input_data,
        prediction=prediction,
        recommendation_id=recommendation_id,
        decision=decision,
        result=result
    )
    
    db.add(entry)
    db.commit()
    
    # Emit socket event
    emit_audit_entry({
        'id': entry.id,
        'timestamp': entry.timestamp.isoformat(),
        'event_type': entry.event_type,
        'actor': entry.actor,
        'input_data': entry.input_data,
        'prediction': entry.prediction,
        'recommendation_id': entry.recommendation_id,
        'decision': entry.decision,
        'result': entry.result
    })
