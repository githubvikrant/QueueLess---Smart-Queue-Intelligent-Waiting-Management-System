"""
Counters API endpoints.

This module provides REST API endpoints for counter management:
- Get all counters
- Update counter status

PURPOSE: Provide HTTP interface for counter operations
DEPENDENCIES: FastAPI, SQLAlchemy, app.database.models, app.schemas, app.core.events
SIDE EFFECTS: Modifies database, emits socket events
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app.database.db import get_db
from app.database.models import Counter, Token
from app.schemas.queue import CounterResponse, CounterUpdate
from app.services.eta_service import calculate_all_etas
from app.services.queue_engine import log_audit_entry
from app.core.events import emit_queue_updated, emit_eta_updated

# Create API router
router = APIRouter()


@router.get("/", response_model=List[CounterResponse])
def get_counters(db: Session = Depends(get_db)):
    """
    PURPOSE: Get all counters with their current state
    
    PARAMETERS:
        db: Database session (injected by FastAPI)
    
    RETURNS: List of CounterResponse objects with current token info
    
    WORKFLOW:
        1. Query all counters
        2. For each counter, include current token details if any
        3. Return list with status and expected_free_at
    
    DEPENDENCIES: Counter, Token models
    SIDE EFFECTS: None (read-only)
    
    USAGE: Frontend calls this to display counter status on dashboard
    """
    counters = db.query(Counter).all()
    
    result = []
    for counter in counters:
        # Get current token if any
        current_token = None
        if counter.current_token_id:
            token = db.query(Token).filter(Token.id == counter.current_token_id).first()
            if token:
                current_token = {
                    'id': token.id,
                    'service_name': token.service_type.name if token.service_type else None,
                    'status': token.status
                }
        
        counter_dict = {
            'id': counter.id,
            'name': counter.name,
            'status': counter.status,
            'supported_services': counter.supported_services,
            'current_token_id': counter.current_token_id,
            'current_token': current_token,
            'expected_free_at': counter.expected_free_at
        }
        result.append(CounterResponse(**counter_dict))
    
    return result


@router.post("/{counter_id}/status")
def update_counter_status(
    counter_id: str,
    status: str = Query(..., description="New status (AVAILABLE, BUSY, CLOSED)"),
    db: Session = Depends(get_db)
):
    """
    PURPOSE: Update a counter's status
    
    PARAMETERS:
        counter_id: Counter ID (e.g., "A", "B")
        status: New status (AVAILABLE, BUSY, CLOSED)
        db: Database session (injected by FastAPI)
    
    RETURNS: Updated CounterResponse object
    
    WORKFLOW:
        1. Get the counter
        2. If not found, raise 404 error
        3. Update counter status
        4. Recalculate ETAs for all waiting tokens
        5. Emit queue:updated event
        6. Log to audit trail
        7. Return updated counter
    
    DEPENDENCIES: calculate_all_etas, emit_queue_updated
    SIDE EFFECTS: Updates counter status, recalculates ETAs, emits events
    
    USAGE: Frontend calls this to open/close counters or change availability
    """
    # Validate status
    valid_statuses = ["AVAILABLE", "BUSY", "CLOSED"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    counter = db.query(Counter).filter(Counter.id == counter_id).first()
    if not counter:
        raise HTTPException(status_code=404, detail=f"Counter {counter_id} not found")
    
    # Update status
    old_status = counter.status
    counter.status = status
    
    # If closing counter, clear current token
    if status == "CLOSED" and counter.current_token_id:
        counter.current_token_id = None
        counter.expected_free_at = None
    
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_queue_updated({'counter_id': counter_id, 'old_status': old_status, 'new_status': status})
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="COUNTER_STATUS_CHANGED",
        actor="RECEPTIONIST",
        input_data={'counter_id': counter_id, 'old_status': old_status, 'new_status': status},
        result={'status': status}
    )
    
    # Return updated counter
    counters = get_counters(db)
    for c in counters:
        if c.id == counter_id:
            return c
    
    raise HTTPException(status_code=404, detail=f"Counter {counter_id} not found after update")
