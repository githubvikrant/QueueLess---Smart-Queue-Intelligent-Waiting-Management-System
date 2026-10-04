"""
No-show service - Grace timer logic for patient no-shows.

This service handles the grace timer when a token is called.
If the patient doesn't respond within the grace period, the token is marked as no-show.

PURPOSE: Manage no-show grace timer and recovery
DEPENDENCIES: SQLAlchemy, app.database.models, app.services.eta_service, app.core.config, asyncio
SIDE EFFECTS: Updates token status, recalculates ETAs, emits socket events
"""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional
from app.database.models import Token
from app.services.eta_service import calculate_all_etas
from app.services.queue_engine import log_audit_entry
from app.core.config import settings
from app.core.events import emit_token_no_show, emit_eta_updated


# Dictionary to track active grace timers
# Key: token_id, Value: asyncio.Task
active_grace_timers = {}


async def start_grace_timer(token_id: str, db: Session):
    """
    PURPOSE: Start an async grace timer for a called token
    
    PARAMETERS:
        token_id: ID of the token that was called
        db: Database session
    
    WORKFLOW:
        1. Check if grace timer already exists for this token
        2. If yes, cancel it
        3. Create new async task to wait for grace period
        4. After grace period expires, mark token as no-show
        5. Recalculate ETAs for freed slot
        6. Emit events
        7. Log to audit trail
    
    DEPENDENCIES: settings.no_show_grace_min, mark_as_no_show
    SIDE EFFECTS: Creates async task, may mark token as no-show
    
    USAGE: Called by queue_engine.call_next_token when token is CALLED
    """
    # Cancel existing timer if any
    if token_id in active_grace_timers:
        active_grace_timers[token_id].cancel()
    
    # Create new grace timer task
    task = asyncio.create_task(grace_timer_task(token_id, db))
    active_grace_timers[token_id] = task


async def grace_timer_task(token_id: str, db: Session):
    """
    PURPOSE: Async task that waits for grace period then marks no-show
    
    PARAMETERS:
        token_id: ID of the token
        db: Database session
    
    WORKFLOW:
        1. Wait for no_show_grace_min minutes
        2. Check if token is still CALLED (not IN_SERVICE)
        3. If still CALLED, mark as NO_SHOW
        4. Recalculate ETAs
        5. Emit events
        6. Log to audit trail
        7. Clean up timer from active_grace_timers
    
    DEPENDENCIES: mark_as_no_show, calculate_all_etas
    SIDE EFFECTS: May mark token as no-show, recalculates ETAs
    
    USAGE: Internal function called by start_grace_timer
    """
    try:
        # Wait for grace period
        await asyncio.sleep(settings.no_show_grace_min * 60)
        
        # Check if token still needs to be marked as no-show
        token = db.query(Token).filter(Token.id == token_id).first()
        if token and token.status == "CALLED":
            # Mark as no-show
            mark_as_no_show(token_id, db)
        
    except asyncio.CancelledError:
        # Timer was cancelled (patient responded)
        pass
    finally:
        # Clean up timer
        if token_id in active_grace_timers:
            del active_grace_timers[token_id]


def cancel_grace_timer(token_id: str):
    """
    PURPOSE: Cancel grace timer for a token (patient responded)
    
    PARAMETERS:
        token_id: ID of the token
    
    WORKFLOW:
        1. Check if grace timer exists for this token
        2. If yes, cancel it
        3. Remove from active_grace_timers
    
    DEPENDENCIES: active_grace_timers
    SIDE EFFECTS: Cancels async task, removes from tracking dict
    
    USAGE: Called when patient arrives at counter (token status changes to IN_SERVICE)
    """
    if token_id in active_grace_timers:
        active_grace_timers[token_id].cancel()
        del active_grace_timers[token_id]


def mark_as_no_show(token_id: str, db: Session) -> Optional[Token]:
    """
    PURPOSE: Mark a token as no-show and handle recovery
    
    PARAMETERS:
        token_id: ID of the token to mark as no-show
        db: Database session
    
    RETURNS: Updated Token object, or None if not found
    
    WORKFLOW:
        1. Get the token
        2. Update status to NO_SHOW
        3. Clear assigned counter
        4. Recalculate ETAs for all waiting tokens
        5. Emit token:no_show and eta:updated events
        6. Log to audit trail
        7. Return updated token
    
    DEPENDENCIES: calculate_all_etas, emit_token_no_show, emit_eta_updated
    SIDE EFFECTS: Updates token status, recalculates ETAs, emits events
    
    USAGE: Called by grace timer or demo control
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        return None
    
    # Update token status
    old_status = token.status
    token.status = "NO_SHOW"
    token.assigned_counter_id = None
    
    db.commit()
    
    # Recalculate ETAs
    eta_result = calculate_all_etas(db)
    
    # Emit events
    emit_token_no_show(token_id)
    emit_eta_updated(eta_result['affected_token_ids'], eta_result['eta_snapshots'])
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="NO_SHOW_DETECTED",
        actor="SYSTEM",
        input_data={'token_id': token_id, 'old_status': old_status},
        result={'status': 'NO_SHOW', 'affected_token_ids': eta_result['affected_token_ids']}
    )
    
    return token


def get_active_grace_timers() -> list:
    """
    PURPOSE: Get list of tokens with active grace timers
    
    PARAMETERS: None
    
    RETURNS: List of token IDs with active grace timers
    
    WORKFLOW:
        1. Return keys from active_grace_timers dictionary
    
    DEPENDENCIES: active_grace_timers
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called for monitoring or debugging
    """
    return list(active_grace_timers.keys())
