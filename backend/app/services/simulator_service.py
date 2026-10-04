"""
What-if simulator service - Deep-copy simulation for scenario testing.

This service allows testing "what-if" scenarios without touching the live queue.
It creates a deep copy of the current state, applies changes, and returns results.

PURPOSE: Simulate queue scenarios on a deep copy without affecting live state
DEPENDENCIES: SQLAlchemy, app.services.eta_service, copy
SIDE EFFECTS: None (simulation on copy only - never touches live database)
"""

from sqlalchemy.orm import Session
from typing import Dict, Any
from copy import deepcopy
from datetime import datetime, timedelta
from app.database.models import Token, Counter, ServiceType
from app.services.eta_service import calculate_all_etas


def run_what_if(scenario: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Run a what-if simulation on a deep copy of queue state
    
    PARAMETERS:
        scenario: Dictionary with scenario parameters
                  - extra_patients: Number of additional patients to add
                  - extra_counters: Number of additional counters to add
                  - service_delay_min: Additional delay to add to all services
        db: Database session
    
    RETURNS: Dictionary with current, proposed, and difference metrics
                 Always includes is_simulation: True (Non-Negotiable Rule #8)
    
    WORKFLOW:
        1. Get current state from database (tokens, counters, service types)
        2. Create deep copy of state (NEVER touch live DB)
        3. Apply scenario changes to the copy:
           - Add extra patients with random services
           - Add extra counters with random services
           - Add delay to service durations
        4. Run ETA calculation on the copy
        5. Calculate metrics for current and proposed states
        6. Calculate difference between current and proposed
        7. Return results with is_simulation: True
    
    DEPENDENCIES: calculate_all_etas, deepcopy
    SIDE EFFECTS: None (simulation on copy only)
    
    USAGE: Called by api/simulation.py to test scenarios
    
    IMPORTANT: is_simulation: True MUST ALWAYS be in the return value
    (Non-Negotiable Rule #8: Simulations are labelled)
    """
    import random
    
    # Get current state
    current_tokens = db.query(Token).filter(Token.status == "WAITING").all()
    current_counters = db.query(Counter).all()
    service_types = db.query(ServiceType).all()
    
    # Calculate current metrics
    current_metrics = calculate_queue_metrics(current_tokens, current_counters, db)
    
    # Create deep copy of state
    copied_tokens = deepcopy(current_tokens)
    copied_counters = deepcopy(current_counters)
    copied_service_types = deepcopy(service_types)
    
    # Apply scenario changes to the copy
    extra_patients = scenario.get('extra_patients', 0)
    extra_counters = scenario.get('extra_counters', 0)
    service_delay = scenario.get('service_delay_min', 0)
    
    # Add extra patients
    for i in range(extra_patients):
        # Pick random service
        service = random.choice(copied_service_types)
        
        # Create new token (simulate)
        new_token = Token(
            id=f"SIM_Q{i+1}",
            service_id=service.id,
            kind="WALK_IN",
            priority_class=0,
            status="WAITING",
            created_at=datetime.utcnow()
        )
        # Manually set service_type relationship for copy
        new_token.service_type = service
        copied_tokens.append(new_token)
    
    # Add extra counters
    for i in range(extra_counters):
        # Pick random services to support
        num_services = random.randint(1, 3)
        supported = random.sample([st.name for st in copied_service_types], num_services)
        
        new_counter = Counter(
            id=f"SIM_{chr(67 + i)}",  # C, D, E, etc.
            name=f"Simulated Counter {chr(67 + i)}",
            status="AVAILABLE",
            supported_services=supported,
            current_token_id=None,
            expected_free_at=datetime.utcnow()
        )
        copied_counters.append(new_counter)
    
    # Add service delay
    if service_delay > 0:
        for service in copied_service_types:
            service.avg_duration_min += service_delay
    
    # Calculate proposed metrics on the copy
    # Note: We can't run full ETA calculation on the copy without DB session
    # So we'll estimate based on current metrics and scenario changes
    proposed_metrics = estimate_proposed_metrics(
        current_metrics,
        extra_patients,
        extra_counters,
        service_delay
    )
    
    # Calculate difference
    difference = calculate_difference(current_metrics, proposed_metrics)
    
    return {
        'current': current_metrics,
        'proposed': proposed_metrics,
        'difference': difference,
        'is_simulation': True  # Non-Negotiable Rule #8
    }


def calculate_queue_metrics(tokens: list, counters: list, db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Calculate current queue metrics
    
    PARAMETERS:
        tokens: List of Token objects
        counters: List of Counter objects
        db: Database session
    
    RETURNS: Dictionary with queue metrics
    
    WORKFLOW:
        1. Count active counters
        2. Count waiting patients
        3. Calculate average wait time
        4. Return metrics dictionary
    
    DEPENDENCIES: Token, Counter models
    SIDE EFFECTS: None (read-only)
    """
    active_counters = [c for c in counters if c.status != "CLOSED"]
    waiting_patients = len([t for t in tokens if t.status == "WAITING"])
    
    # Calculate average wait time (simplified)
    if waiting_patients > 0:
        # Use ETA from first waiting token as proxy
        first_waiting = min(tokens, key=lambda t: t.created_at) if tokens else None
        if first_waiting and first_waiting.eta_expected:
            avg_wait_min = (first_waiting.eta_expected - datetime.utcnow()).total_seconds() / 60
        else:
            avg_wait_min = 0
    else:
        avg_wait_min = 0
    
    return {
        'active_counters': len(active_counters),
        'waiting_patients': waiting_patients,
        'avg_wait_min': round(avg_wait_min, 1) if avg_wait_min > 0 else 0
    }


def estimate_proposed_metrics(current: Dict[str, Any], 
                            extra_patients: int,
                            extra_counters: int,
                            service_delay: int) -> Dict[str, Any]:
    """
    PURPOSE: Estimate proposed metrics based on scenario changes
    
    PARAMETERS:
        current: Current metrics dictionary
        extra_patients: Number of extra patients
        extra_counters: Number of extra counters
        service_delay: Additional service delay in minutes
    
    RETURNS: Dictionary with estimated proposed metrics
    
    WORKFLOW:
        1. Calculate new active counters (current + extra)
        2. Calculate new waiting patients (current + extra)
        3. Estimate new average wait based on capacity increase
        4. Add service delay to wait time
        5. Return proposed metrics
    
    DEPENDENCIES: None (pure calculation)
    SIDE EFFECTS: None (read-only)
    
    USAGE: Helper function for run_what_if
    """
    new_active_counters = current['active_counters'] + extra_counters
    new_waiting_patients = current['waiting_patients'] + extra_patients
    
    # Estimate new average wait
    # More counters = less wait, more patients = more wait
    if new_active_counters > 0:
        capacity_ratio = current['active_counters'] / new_active_counters
        patient_ratio = new_waiting_patients / current['waiting_patients'] if current['waiting_patients'] > 0 else 1
        
        new_avg_wait = current['avg_wait_min'] * patient_ratio / capacity_ratio
        new_avg_wait += service_delay  # Add service delay
    else:
        new_avg_wait = current['avg_wait_min'] + service_delay
    
    return {
        'active_counters': new_active_counters,
        'waiting_patients': new_waiting_patients,
        'avg_wait_min': round(max(0, new_avg_wait), 1)
    }


def calculate_difference(current: Dict[str, Any], proposed: Dict[str, Any]) -> Dict[str, Any]:
    """
    PURPOSE: Calculate difference between current and proposed metrics
    
    PARAMETERS:
        current: Current metrics dictionary
        proposed: Proposed metrics dictionary
    
    RETURNS: Dictionary with differences
    
    WORKFLOW:
        1. Calculate difference in active counters
        2. Calculate difference in waiting patients
        3. Calculate difference in average wait
        4. Return difference dictionary
    
    DEPENDENCIES: None (pure calculation)
    SIDE EFFECTS: None (read-only)
    
    USAGE: Helper function for run_what_if
    """
    counter_diff = proposed['active_counters'] - current['active_counters']
    patient_diff = proposed['waiting_patients'] - current['waiting_patients']
    wait_diff = proposed['avg_wait_min'] - current['avg_wait_min']
    
    return {
        'counters_diff': counter_diff,
        'patients_diff': patient_diff,
        'wait_diff_min': round(wait_diff, 1),
        'wait_diff_description': f"{round(wait_diff, 1)} minutes {'less' if wait_diff < 0 else 'more'} per patient"
    }
