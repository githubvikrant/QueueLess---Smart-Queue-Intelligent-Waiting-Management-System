"""
Bottleneck detection service.

This is the STAR feature - detects overloaded counters and recommends fixes.
Pure code, no AI involved. Uses the ETA engine to compute projected waits.

PURPOSE: Detect bottlenecks (overloaded counters) and generate candidate fix actions
DEPENDENCIES: SQLAlchemy, app.database.models, app.services.eta_service, app.core.config
SIDE EFFECTS: None (read-only detection and candidate generation)
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from app.database.models import Token, Counter
from app.services.eta_service import calculate_all_etas
from app.core.config import settings


def find_bottlenecks(db: Session) -> List[Dict[str, Any]]:
    """
    PURPOSE: Find all counters that are overloaded (bottlenecks)
    
    PARAMETERS:
        db: SQLAlchemy database session
    
    RETURNS: List of bottleneck dictionaries with counter info and affected tokens
    
    WORKFLOW:
        1. Recalculate ETAs for all tokens using eta_service
        2. For each counter:
           a. Get all tokens assigned to or eligible for this counter
           b. Calculate projected wait time for the last token in queue
           c. If projected wait > bottleneck_threshold_min, mark as bottleneck
        3. For each bottleneck:
           a. Find idle counters that can help
           b. Identify affected tokens
           c. Calculate projected wait times
        4. Return list of bottleneck dictionaries
    
    BOTTLENECK DEFINITION:
        A counter is a bottleneck if its projected wait time exceeds
        bottleneck_threshold_min (default: 15 minutes)
    
    DEPENDENCIES: calculate_all_etas, settings.bottleneck_threshold_min
    SIDE EFFECTS: None (read-only detection)
    
    USAGE: Called by agent_service to detect problems that need fixing
    """
    # Recalculate ETAs to get current state
    eta_result = calculate_all_etas(db)
    
    # Get all counters
    counters = db.query(Counter).all()
    
    bottlenecks = []
    
    for counter in counters:
        # Get tokens assigned to this counter
        assigned_tokens = db.query(Token).filter(
            Token.assigned_counter_id == counter.id,
            Token.status == "WAITING"
        ).all()
        
        if not assigned_tokens:
            continue  # No bottleneck if no tokens waiting
        
        # Calculate projected wait for the last token in queue
        # Projected wait = (last token's ETA - now) in minutes
        now = datetime.utcnow()
        last_token = assigned_tokens[-1]  # Last in queue
        
        if last_token.eta_expected:
            projected_wait_min = (last_token.eta_expected - now).total_seconds() / 60
            
            # Check if this exceeds bottleneck threshold
            if projected_wait_min > settings.bottleneck_threshold_min:
                # Find idle counters that can help
                idle_counters = find_idle_counters(db, counter)
                
                # Identify affected tokens
                affected_tokens = [
                    {
                        'id': t.id,
                        'service': t.service_type.name,
                        'eta': t.eta_expected.isoformat() if t.eta_expected else None
                    }
                    for t in assigned_tokens
                ]
                
                bottlenecks.append({
                    'overloaded_counter': {
                        'id': counter.id,
                        'name': counter.name,
                        'projected_wait_min': projected_wait_min
                    },
                    'idle_counters': idle_counters,
                    'affected_tokens': affected_tokens,
                    'affected_token_ids': [t.id for t in assigned_tokens]
                })
    
    return bottlenecks


def find_idle_counters(db: Session, overloaded_counter: Counter) -> List[Dict[str, Any]]:
    """
    PURPOSE: Find idle counters that can help with an overloaded counter
    
    PARAMETERS:
        db: SQLAlchemy database session
        overloaded_counter: The counter that is overloaded
    
    RETURNS: List of idle counter dictionaries
    
    WORKFLOW:
        1. Query all counters except the overloaded one
        2. Filter for counters with status = AVAILABLE
        3. Check if they support any of the services in the overloaded queue
        4. Return list of eligible idle counters
    
    DEPENDENCIES: Counter model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by find_bottlenecks to identify potential help
    """
    # Get services from overloaded counter's queue
    overloaded_services = set()
    tokens = db.query(Token).filter(
        Token.assigned_counter_id == overloaded_counter.id,
        Token.status == "WAITING"
    ).all()
    
    for token in tokens:
        overloaded_services.add(token.service_type.name)
    
    # Find idle counters that support any of these services
    idle_counters = db.query(Counter).filter(
        Counter.id != overloaded_counter.id,
        Counter.status == "AVAILABLE"
    ).all()
    
    eligible_idle = []
    for counter in idle_counters:
        # Check if counter supports any of the overloaded services
        supported = set(counter.supported_services)
        if supported.intersection(overloaded_services):
            eligible_idle.append({
                'id': counter.id,
                'name': counter.name,
                'supported_services': counter.supported_services,
                'common_services': list(supported.intersection(overloaded_services))
            })
    
    return eligible_idle


def generate_candidate_actions(bottleneck: Dict[str, Any], db: Session) -> List[Dict[str, Any]]:
    """
    PURPOSE: Generate candidate actions to resolve a bottleneck
    
    PARAMETERS:
        bottleneck: Bottleneck dictionary from find_bottlenecks
        db: SQLAlchemy database session
    
    RETURNS: List of candidate action dictionaries
    
    WORKFLOW:
        1. For each idle counter that can help:
           a. For each affected token that the idle counter can serve:
              i. Calculate wait time before reassignment
              ii. Calculate wait time after reassignment
              iii. Create candidate REASSIGN action
        2. Return list of candidate actions sorted by wait reduction
    
    CANDIDATE ACTION FORMAT:
        {
            'type': 'REASSIGN',
            'token_id': 'Q103',
            'from_counter_id': 'A',
            'to_counter_id': 'B',
            'wait_before_min': 22.5,
            'wait_after_min': 8.0,
            'reason': 'Reduce wait by 14.5 minutes'
        }
    
    DEPENDENCIES: find_idle_counters, eta_service (for wait calculations)
    SIDE EFFECTS: None (read-only candidate generation)
    
    USAGE: Called by agent_service to get actionable recommendations
    """
    overloaded_counter = bottleneck['overloaded_counter']
    idle_counters = bottleneck['idle_counters']
    affected_tokens = bottleneck['affected_tokens']
    
    candidates = []
    
    for idle_counter in idle_counters:
        counter_id = idle_counter['id']
        supported_services = set(idle_counter['supported_services'])
        
        for token_info in affected_tokens:
            token_id = token_info['id']
            service = token_info['service']
            
            # Check if idle counter supports this token's service
            if service in supported_services:
                # Get token from database
                token = db.query(Token).filter(Token.id == token_id).first()
                if not token:
                    continue
                
                # Calculate wait before (from bottleneck info)
                wait_before = overloaded_counter['projected_wait_min']
                
                # Calculate wait after (assume idle counter is immediately available)
                # Simplified: wait after = service duration
                wait_after = token.service_type.avg_duration_min
                
                # Calculate savings
                savings = wait_before - wait_after
                
                if savings > 0:
                    candidates.append({
                        'type': 'REASSIGN',
                        'token_id': token_id,
                        'from_counter_id': overloaded_counter['id'],
                        'to_counter_id': counter_id,
                        'wait_before_min': round(wait_before, 1),
                        'wait_after_min': round(wait_after, 1),
                        'savings_min': round(savings, 1),
                        'reason': f'Reassign {token_id} from {overloaded_counter["id"]} to {counter_id}, saving {round(savings, 1)} minutes'
                    })
    
    # Sort by savings (descending) - most impactful actions first
    candidates.sort(key=lambda x: x['savings_min'], reverse=True)
    
    return candidates


def detect_single_bottleneck(db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Detect a single bottleneck (for demo purposes)
    
    PARAMETERS:
        db: SQLAlchemy database session
    
    RETURNS: Dictionary with bottleneck info or empty dict if none found
    
    WORKFLOW:
        1. Call find_bottlenecks to get all bottlenecks
        2. Return the first bottleneck if any
        3. Return empty dict if no bottlenecks
    
    DEPENDENCIES: find_bottlenecks
    SIDE EFFECTS: None (read-only)
    
    USAGE: Simplified version for agent_service to get one bottleneck at a time
    """
    bottlenecks = find_bottlenecks(db)
    
    if bottlenecks:
        return bottlenecks[0]
    
    return {}
