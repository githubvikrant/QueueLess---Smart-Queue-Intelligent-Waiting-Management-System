"""
Queue API endpoints.

This module provides REST API endpoints for queue management:
- Get all tokens
- Get single token
- Check-in new patient
- Demo controls (inject delay, add walk-ins, mark no-show)

PURPOSE: Provide HTTP interface for queue operations
DEPENDENCIES: FastAPI, SQLAlchemy, app.services, app.schemas, app.core.events
SIDE EFFECTS: Modifies database, emits socket events
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app.database.db import get_db
from app.database.models import Token, ServiceType
from app.schemas.queue import (
    TokenResponse, TokenCreate, InjectDelayRequest, 
    AddWalkinsRequest, MarkNoshowRequest
)
from app.services.queue_engine import (
    get_ordered_queue, generate_token_id, complete_service, log_audit_entry
)
from app.services.eta_service import calculate_all_etas
from app.core.events import emit_queue_updated, emit_eta_updated, emit_token_no_show

# Create API router
router = APIRouter()


@router.get("/", response_model=List[TokenResponse])
def get_queue(db: Session = Depends(get_db)):
    """
    PURPOSE: Get all tokens ordered by queue position
    
    PARAMETERS:
        db: Database session (injected by FastAPI)
    
    RETURNS: List of TokenResponse objects with ETA information
    
    WORKFLOW:
        1. Call get_ordered_queue to get tokens in correct order
        2. For each token, include service name and counter name
        3. Return list with ETA fields populated
    
    DEPENDENCIES: get_ordered_queue, Token model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Frontend calls this to display the live queue board
    """
    tokens = get_ordered_queue(db)
    
    # Enrich with service name and counter name
    result = []
    for token in tokens:
        token_dict = {
            'id': token.id,
            'service_id': token.service_id,
            'service_name': token.service_type.name if token.service_type else None,
            'kind': token.kind,
            'appointment_time': token.appointment_time,
            'priority_class': token.priority_class,
            'status': token.status,
            'assigned_counter_id': token.assigned_counter_id,
            'assigned_counter_name': token.assigned_counter.name if token.assigned_counter else None,
            'created_at': token.created_at,
            'called_at': token.called_at,
            'eta_low': token.eta_low,
            'eta_expected': token.eta_expected,
            'eta_high': token.eta_high,
            'eta_reason': token.eta_reason
        }
        result.append(TokenResponse(**token_dict))
    
    return result


@router.get("/{token_id}", response_model=TokenResponse)
def get_token(token_id: str, db: Session = Depends(get_db)):
    """
    PURPOSE: Get a single token by ID
    
    PARAMETERS:
        token_id: Token ID (e.g., "Q101")
        db: Database session (injected by FastAPI)
    
    RETURNS: TokenResponse object with full details
    
    WORKFLOW:
        1. Query token by ID
        2. If not found, raise 404 error
        3. Return token with service name and counter name
    
    DEPENDENCIES: Token model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Frontend calls this for patient view (patient looks up their token)
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {token_id} not found")
    
    token_dict = {
        'id': token.id,
        'service_id': token.service_id,
        'service_name': token.service_type.name if token.service_type else None,
        'kind': token.kind,
        'appointment_time': token.appointment_time,
        'priority_class': token.priority_class,
        'status': token.status,
        'assigned_counter_id': token.assigned_counter_id,
        'assigned_counter_name': token.assigned_counter.name if token.assigned_counter else None,
        'created_at': token.created_at,
        'called_at': token.called_at,
        'eta_low': token.eta_low,
        'eta_expected': token.eta_expected,
        'eta_high': token.eta_high,
        'eta_reason': token.eta_reason
    }
    
    return TokenResponse(**token_dict)


@router.post("/checkin", response_model=TokenResponse)
def checkin(
    service: str = Query(..., description="Service name (e.g., 'Blood Test')"),
    kind: str = Query(default="WALK_IN", description="Token type (WALK_IN or APPOINTMENT)"),
    db: Session = Depends(get_db)
):
    """
    PURPOSE: Register a new patient (check-in)
    
    PARAMETERS:
        service: Service name (e.g., "Blood Test", "ECG", "Consultation")
        kind: Token type (WALK_IN or APPOINTMENT)
        db: Database session (injected by FastAPI)
    
    RETURNS: Newly created TokenResponse object
    
    WORKFLOW:
        1. Find service type by name
        2. If not found, raise 404 error
        3. Generate next token ID using generate_token_id
        4. Create new Token record with status=WAITING
        5. Recalculate ETAs for all waiting tokens
        6. Emit queue:updated event
        7. Log to audit trail
        8. Return new token
    
    DEPENDENCIES: generate_token_id, calculate_all_etas, emit_queue_updated
    SIDE EFFECTS: Creates token, recalculates ETAs, emits events
    
    USAGE: Frontend calls this when a new patient checks in
    """
    # Find service type
    service_type = db.query(ServiceType).filter(ServiceType.name == service).first()
    if not service_type:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not found")
    
    # Generate token ID
    token_id = generate_token_id(db)
    
    # Create new token
    new_token = Token(
        id=token_id,
        service_id=service_type.id,
        kind=kind,
        priority_class=0,
        status="WAITING"
    )
    
    db.add(new_token)
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_queue_updated({'token_id': token_id, 'new_status': 'WAITING'})
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="PATIENT_CHECKIN",
        actor="RECEPTIONIST",
        input_data={'token_id': token_id, 'service': service, 'kind': kind},
        result={'status': 'WAITING'}
    )
    
    # Return created token
    return get_token(token_id, db)


@router.post("/demo/inject-delay")
def inject_delay(request: InjectDelayRequest, db: Session = Depends(get_db)):
    """
    PURPOSE: Inject delay into a counter (demo control)
    
    PARAMETERS:
        request: InjectDelayRequest with counter_id and extra_minutes
        db: Database session (injected by FastAPI)
    
    RETURNS: Dictionary with counter_id, new_free_at, and affected_token_ids
    
    WORKFLOW:
        1. Get the counter
        2. If not found, raise 404 error
        3. Add extra_minutes to counter.expected_free_at
        4. Recalculate ETAs for all waiting tokens
        5. Emit eta:updated event
        6. Log to audit trail
        7. Return result
    
    DEPENDENCIES: calculate_all_etas, emit_eta_updated
    SIDE EFFECTS: Updates counter, recalculates ETAs, emits events
    
    USAGE: Demo control to simulate a delay at a counter
    """
    from app.database.models import Counter
    from datetime import timedelta
    
    counter = db.query(Counter).filter(Counter.id == request.counter_id).first()
    if not counter:
        raise HTTPException(status_code=404, detail=f"Counter {request.counter_id} not found")
    
    # Add delay to expected_free_at
    if counter.expected_free_at:
        counter.expected_free_at += timedelta(minutes=request.extra_minutes)
    else:
        from datetime import datetime
        counter.expected_free_at = datetime.utcnow() + timedelta(minutes=request.extra_minutes)
    
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="DELAY_INJECTED",
        actor="RECEPTIONIST",
        input_data={'counter_id': request.counter_id, 'extra_minutes': request.extra_minutes},
        result={'new_free_at': counter.expected_free_at.isoformat() if counter.expected_free_at else None}
    )
    
    return {
        'counter_id': request.counter_id,
        'new_free_at': counter.expected_free_at.isoformat() if counter.expected_free_at else None,
        'affected_token_ids': eta_result['affected_token_ids']
    }


@router.post("/demo/add-walkins")
def add_walkins(request: AddWalkinsRequest, db: Session = Depends(get_db)):
    """
    PURPOSE: Add multiple walk-in patients (demo control)
    
    PARAMETERS:
        request: AddWalkinsRequest with count of walk-ins to add
        db: Database session (injected by FastAPI)
    
    RETURNS: List of newly created token IDs
    
    WORKFLOW:
        1. Get all service types
        2. For each walk-in to add:
           a. Pick a random service
           b. Generate token ID
           c. Create token with status=WAITING
        3. Recalculate ETAs for all waiting tokens
        4. Emit queue:updated event
        5. Log to audit trail
        6. Return list of new token IDs
    
    DEPENDENCIES: generate_token_id, calculate_all_etas, emit_queue_updated
    SIDE EFFECTS: Creates tokens, recalculates ETAs, emits events
    
    USAGE: Demo control to simulate a rush of walk-in patients
    """
    import random
    
    service_types = db.query(ServiceType).all()
    if not service_types:
        raise HTTPException(status_code=404, detail="No service types found")
    
    new_token_ids = []
    
    for _ in range(request.count):
        # Pick random service
        service = random.choice(service_types)
        
        # Generate token ID
        token_id = generate_token_id(db)
        
        # Create token
        new_token = Token(
            id=token_id,
            service_id=service.id,
            kind="WALK_IN",
            priority_class=0,
            status="WAITING"
        )
        
        db.add(new_token)
        new_token_ids.append(token_id)
    
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_queue_updated({'new_tokens': new_token_ids})
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="WALKINS_ADDED",
        actor="RECEPTIONIST",
        input_data={'count': request.count},
        result={'new_token_ids': new_token_ids}
    )
    
    return {'new_token_ids': new_token_ids}


@router.post("/demo/mark-noshow")
def mark_noshow(request: MarkNoshowRequest, db: Session = Depends(get_db)):
    """
    PURPOSE: Mark a token as no-show (demo control)
    
    PARAMETERS:
        request: MarkNoshowRequest with token_id
        db: Database session (injected by FastAPI)
    
    RETURNS: Dictionary with token_id and new status
    
    WORKFLOW:
        1. Get the token
        2. If not found, raise 404 error
        3. Update token status to NO_SHOW
        4. Recalculate ETAs for all waiting tokens
        5. Emit token:no_show and eta:updated events
        6. Log to audit trail
        7. Return result
    
    DEPENDENCIES: calculate_all_etas, emit_token_no_show, emit_eta_updated
    SIDE EFFECTS: Updates token status, recalculates ETAs, emits events
    
    USAGE: Demo control to simulate a patient not showing up
    """
    token = db.query(Token).filter(Token.id == request.token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {request.token_id} not found")
    
    # Update status
    token.status = "NO_SHOW"
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_token_no_show(request.token_id)
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="NO_SHOW_MARKED",
        actor="RECEPTIONIST",
        input_data={'token_id': request.token_id},
        result={'status': 'NO_SHOW'}
    )
    
    return {
        'token_id': request.token_id,
        'status': 'NO_SHOW'
    }
