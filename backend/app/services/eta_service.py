"""
ETA (Estimated Time of Arrival) calculation engine.

This is the STAR feature - the foundation of the entire system.
Every other feature depends on accurate ETA calculations.

The algorithm is purely deterministic - no AI involved.
It calculates ETAs based on counter availability and service durations.

PURPOSE: Calculate accurate ETAs with uncertainty ranges for all waiting tokens
DEPENDENCIES: SQLAlchemy, app.database.models, datetime
SIDE EFFECTS: Updates Token.eta_* fields in database, emits socket events
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from app.database.models import Token, Counter, ServiceType


def expected_duration(service: ServiceType) -> float:
    """
    PURPOSE: Get expected duration for a service based on rolling average
    
    PARAMETERS:
        service: ServiceType ORM object
    
    RETURNS: Expected duration in minutes (float)
    
    WORKFLOW:
        1. Return the avg_duration_min from the service
        2. This is a rolling average of recent actual durations
    
    DEPENDENCIES: ServiceType model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by calculate_all_etas to estimate how long each token will take
    """
    return service.avg_duration_min


def get_service_spread(service: ServiceType) -> float:
    """
    PURPOSE: Get spread (standard deviation) for a service
    
    PARAMETERS:
        service: ServiceType ORM object
    
    RETURNS: Spread in minutes (float)
    
    WORKFLOW:
        1. Return the spread_min from the service
        2. This represents the uncertainty in duration estimates
    
    DEPENDENCIES: ServiceType model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by calculate_all_etas to calculate ETA uncertainty range
    """
    return service.spread_min


def calculate_counter_free_at(counter: Counter, now: datetime) -> datetime:
    """
    PURPOSE: Calculate when a counter will be free to serve the next patient
    
    PARAMETERS:
        counter: Counter ORM object
        now: Current datetime
    
    RETURNS: Datetime when counter will be available
    
    WORKFLOW:
        1. If counter has expected_free_at set and it's in the future, use it
        2. If counter is idle (no expected_free_at or in the past), return now
        3. This accounts for tokens currently in service
    
    DEPENDENCIES: Counter model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by calculate_all_etas to determine counter availability
    """
    if counter.expected_free_at and counter.expected_free_at > now:
        return counter.expected_free_at
    return now


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
    
    USAGE: Called by calculate_all_etas to process tokens in queue order
    """
    return db.query(Token).filter(Token.status == "WAITING").order_by(
        Token.priority_class.desc(),
        Token.created_at.asc()
    ).all()


def is_counter_eligible(counter: Counter, token: Token) -> bool:
    """
    PURPOSE: Check if a counter can serve a token's service
    
    PARAMETERS:
        counter: Counter ORM object
        token: Token ORM object
    
    RETURNS: True if counter supports the token's service, False otherwise
    
    WORKFLOW:
        1. Get the token's service name
        2. Check if it's in the counter's supported_services list
        3. Return True if supported, False otherwise
    
    DEPENDENCIES: Counter, Token, ServiceType models
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by calculate_all_etas to assign tokens to eligible counters
    """
    service_name = token.service_type.name
    return service_name in counter.supported_services


def calculate_all_etas(db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Recalculate ETAs for all WAITING tokens based on current state
    
    PARAMETERS:
        db: SQLAlchemy database session
    
    RETURNS: Dictionary with affected_token_ids list and eta snapshots
    
    WORKFLOW:
        1. Get current time
        2. Get all counters and calculate their free_at times
        3. Get ordered queue of WAITING tokens
        4. For each token in queue order:
           a. Find the earliest eligible counter (based on free_at)
           b. Calculate token's ETA as that counter's free_at
           c. Add service duration to counter's free_at (for next token)
           d. Calculate eta_low = eta_expected - K * spread
           e. Calculate eta_high = eta_expected + K * spread
           f. Update token's ETA fields in database
        5. Track which tokens were affected
        6. Return list of affected token IDs and snapshots
    
    ALGORITHM DETAILS:
        - K = 1.0 for uncertainty range (configurable)
        - Spread comes from service's spread_min field
        - Counter free_at accounts for current token in service
        - Tokens are assigned to earliest eligible counter
    
    DEPENDENCIES: calculate_counter_free_at, get_ordered_queue, is_counter_eligible,
                  expected_duration, get_service_spread
    SIDE EFFECTS: Updates Token.eta_* fields in database
    
    USAGE: Called whenever state changes (token completed, counter status changed, etc.)
    
    NOTE: This is the STAR feature - must be built first as everything depends on it
    """
    now = datetime.utcnow()
    K = 1.0  # Uncertainty multiplier (could be configurable)
    
    # Get all counters
    counters = db.query(Counter).all()
    
    # Calculate when each counter will be free
    counter_free_at = {}
    for counter in counters:
        counter_free_at[counter.id] = calculate_counter_free_at(counter, now)
    
    # Get ordered queue of waiting tokens
    waiting_tokens = get_ordered_queue(db)
    
    # Track affected tokens and their old ETAs for snapshots
    affected_token_ids = []
    eta_snapshots = {}
    
    # Calculate ETA for each token
    for token in waiting_tokens:
        # Save old ETA for snapshot
        old_eta = token.eta_expected
        eta_snapshots[token.id] = {
            'old_eta': old_eta.isoformat() if old_eta else None
        }
        
        # Find the earliest eligible counter
        best_counter_id = None
        best_free_at = None
        
        for counter in counters:
            if is_counter_eligible(counter, token):
                counter_free = counter_free_at[counter.id]
                if best_free_at is None or counter_free < best_free_at:
                    best_free_at = counter_free
                    best_counter_id = counter.id
        
        # Assign token to best counter
        if best_counter_id:
            token.eta_expected = best_free_at
            token.assigned_counter_id = best_counter_id
            
            # Calculate uncertainty range
            service = token.service_type
            spread = get_service_spread(service)
            duration_uncertainty = timedelta(minutes=K * spread)
            
            token.eta_low = best_free_at - duration_uncertainty
            token.eta_high = best_free_at + duration_uncertainty
            
            # Update counter's free_at for next token
            service_duration = expected_duration(service)
            counter_free_at[best_counter_id] += timedelta(minutes=service_duration)
            
            # Set reason
            token.eta_reason = f"Assigned to {best_counter_id}, service duration ~{service_duration}min"
            
            affected_token_ids.append(token.id)
            
            # Save new ETA for snapshot
            eta_snapshots[token.id]['new_eta'] = best_free_at.isoformat()
    
    # Commit changes to database
    db.commit()
    
    return {
        'affected_token_ids': affected_token_ids,
        'eta_snapshots': eta_snapshots
    }


def find_affected_tokens(token_id: str, db: Session) -> List[str]:
    """
    PURPOSE: Find all tokens behind a given token in the queue
    
    PARAMETERS:
        token_id: ID of the token to find affected tokens for
        db: SQLAlchemy database session
    
    RETURNS: List of token IDs that come after the given token in queue order
    
    WORKFLOW:
        1. Get the given token's created_at and priority_class
        2. Find all WAITING tokens with same or lower priority and later created_at
        3. Return list of their IDs
    
    DEPENDENCIES: Token model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called when a token is completed to know which tokens need ETA recalculation
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        return []
    
    # Find tokens behind this one in queue
    affected = db.query(Token).filter(
        Token.status == "WAITING",
        Token.id != token_id,
        Token.priority_class <= token.priority_class,
        Token.created_at > token.created_at
    ).all()
    
    return [t.id for t in affected]
