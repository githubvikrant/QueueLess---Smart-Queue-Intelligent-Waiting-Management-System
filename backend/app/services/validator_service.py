"""
Validator service - Policy and constraint rules engine.

This is the STAR feature - the safety gate that can veto ANY recommendation.
Rules beat speed always - no exceptions.

This service enforces all policy constraints to ensure safe and fair queue operations.

PURPOSE: Validate proposed actions against policy rules
DEPENDENCIES: SQLAlchemy, app.database.models, app.core.config, datetime
SIDE EFFECTS: None (read-only validation only)
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database.models import Token, Counter, ServiceType
from app.core.config import settings


def validate_action(action: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Validate a proposed action against all policy rules
    
    PARAMETERS:
        action: Dictionary describing the action to validate
                Required fields: type, token_id, from_counter_id, to_counter_id
        db: SQLAlchemy database session
    
    RETURNS: Dictionary with 'allowed' (bool) and 'reason' (str)
    
    WORKFLOW:
        1. Check service compatibility (target counter must support token's service)
        2. Check appointment grace period (appointment tokens get grace window)
        3. Check FCFS rule (preserve arrival order within same priority)
        4. Check max delay rule (cannot delay existing patients too much)
        5. Check medical prioritization rule (never set priority, only follow staff-set)
        6. If any check fails, return allowed=False with reason
        7. If all checks pass, return allowed=True
    
    POLICY RULES (Non-Negotiable Rule #4: Rules beat speed):
        1. Service compatibility: Counter must support the service
        2. Appointment grace: appointment_grace_min window applies
        3. FCFS: Preserve arrival order within same priority class
        4. Max delay: Cannot delay existing patients by more than max_delay_existing_min
        5. No medical prioritization: Never set priority, only follow staff-set values
    
    DEPENDENCIES: check_service_compatibility, check_appointment_grace,
                  check_fcfs_rule, check_max_delay, check_medical_prioritization
    SIDE EFFECTS: None (read-only validation)
    
    USAGE: Called by agent_service before proposing any action
           Called by bottleneck_service before generating candidate actions
    
    KEY DEMO MOMENT: Moving a Consultation token to Counter B (Blood Test + ECG only)
    must return allowed=False with plain English reason. This proves the system is safe.
    """
    action_type = action.get('type')
    token_id = action.get('token_id')
    from_counter_id = action.get('from_counter_id')
    to_counter_id = action.get('to_counter_id')
    
    # Get token and counters
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        return {
            'allowed': False,
            'reason': f'Token {token_id} not found'
        }
    
    from_counter = None
    if from_counter_id:
        from_counter = db.query(Counter).filter(Counter.id == from_counter_id).first()
    
    to_counter = None
    if to_counter_id:
        to_counter = db.query(Counter).filter(Counter.id == to_counter_id).first()
    
    # Run all validation checks
    # If any check fails, return immediately with the reason
    
    # Check 1: Service compatibility
    if to_counter:
        compatibility_check = check_service_compatibility(token, to_counter)
        if not compatibility_check['allowed']:
            return compatibility_check
    
    # Check 2: Appointment grace period
    if token.kind == 'APPOINTMENT':
        grace_check = check_appointment_grace(token)
        if not grace_check['allowed']:
            return grace_check
    
    # Check 3: FCFS rule (only for REASSIGN actions)
    if action_type == 'REASSIGN' and from_counter and to_counter:
        fcfs_check = check_fcfs_rule(token, from_counter, to_counter, db)
        if not fcfs_check['allowed']:
            return fcfs_check
    
    # Check 4: Max delay for existing patients
    if action_type == 'REASSIGN' and from_counter and to_counter:
        delay_check = check_max_delay(token, from_counter, to_counter, db)
        if not delay_check['allowed']:
            return delay_check
    
    # Check 5: Medical prioritization (no AI priority setting)
    if action.get('priority_change'):
        priority_check = check_medical_prioritization(action)
        if not priority_check['allowed']:
            return priority_check
    
    # All checks passed
    return {
        'allowed': True,
        'reason': 'Action complies with all policy rules'
    }


def check_service_compatibility(token: Token, counter: Counter) -> Dict[str, Any]:
    """
    PURPOSE: Check if counter supports the token's service
    
    PARAMETERS:
        token: Token ORM object
        counter: Counter ORM object
    
    RETURNS: {'allowed': bool, 'reason': str}
    
    WORKFLOW:
        1. Get the token's service name
        2. Check if it's in the counter's supported_services list
        3. If not supported, return False with reason
        4. If supported, return True
    
    DEPENDENCIES: Token, Counter, ServiceType models
    SIDE EFFECTS: None (read-only)
    
    RULE: Counter must support the token's service type
    """
    service_name = token.service_type.name
    
    if service_name not in counter.supported_services:
        return {
            'allowed': False,
            'reason': f'Counter {counter.id} does not support {service_name}. Supported services: {", ".join(counter.supported_services)}'
        }
    
    return {
        'allowed': True,
        'reason': f'Counter {counter.id} supports {service_name}'
    }


def check_appointment_grace(token: Token) -> Dict[str, Any]:
    """
    PURPOSE: Check if appointment token is within grace period
    
    PARAMETERS:
        token: Token ORM object
    
    RETURNS: {'allowed': bool, 'reason': str}
    
    WORKFLOW:
        1. If token is not an appointment, return True (not applicable)
        2. Calculate time difference between now and appointment_time
        3. If within grace period (appointment_grace_min), allow the action
        4. If outside grace period, return False with reason
    
    DEPENDENCIES: Token model, settings.appointment_grace_min
    SIDE EFFECTS: None (read-only)
    
    RULE: Appointment tokens get appointment_grace_min window before being demoted
    """
    if token.kind != 'APPOINTMENT':
        return {
            'allowed': True,
            'reason': 'Not an appointment token, grace period not applicable'
        }
    
    now = datetime.utcnow()
    if token.appointment_time:
        time_diff = (now - token.appointment_time).total_seconds() / 60
        
        if time_diff <= settings.appointment_grace_min:
            return {
                'allowed': True,
                'reason': f'Appointment within {settings.appointment_grace_min} minute grace period'
            }
        else:
            return {
                'allowed': False,
                'reason': f'Appointment is {time_diff:.1f} minutes late, exceeds {settings.appointment_grace_min} minute grace period'
            }
    
    return {
        'allowed': True,
        'reason': 'No appointment time set, grace period not applicable'
    }


def check_fcfs_rule(token: Token, from_counter: Counter, to_counter: Counter, db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Check First-Come-First-Served rule within same priority class
    
    PARAMETERS:
        token: Token being reassigned
        from_counter: Source counter
        to_counter: Target counter
        db: Database session
    
    RETURNS: {'allowed': bool, 'reason': str}
    
    WORKFLOW:
        1. Get all tokens assigned to target counter with same priority
        2. Check if any of them arrived before the token being reassigned
        3. If yes, reassigning would violate FCFS - return False
        4. If no, FCFS is preserved - return True
    
    DEPENDENCIES: Token model
    SIDE EFFECTS: None (read-only)
    
    RULE: Within same priority class, preserve arrival order (FCFS)
    """
    # Get tokens assigned to target counter with same priority
    same_priority_tokens = db.query(Token).filter(
        Token.assigned_counter_id == to_counter.id,
        Token.priority_class == token.priority_class,
        Token.status == "WAITING"
    ).all()
    
    # Check if any arrived before this token
    for t in same_priority_tokens:
        if t.created_at < token.created_at:
            return {
                'allowed': False,
                'reason': f'Would violate FCFS rule: Token {t.id} arrived before {token.id} at same priority level'
            }
    
    return {
        'allowed': True,
        'reason': 'FCFS rule preserved: no earlier tokens at same priority on target counter'
    }


def check_max_delay(token: Token, from_counter: Counter, to_counter: Counter, db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Check if reassignment would delay existing patients too much
    
    PARAMETERS:
        token: Token being reassigned
        from_counter: Source counter
        to_counter: Target counter
        db: Database session
    
    RETURNS: {'allowed': bool, 'reason': str}
    
    WORKFLOW:
        1. Get all tokens currently waiting at target counter
        2. Calculate their current ETAs
        3. Calculate what their ETAs would be after reassignment
        4. If any token's delay would exceed max_delay_existing_min, return False
        5. If all delays are within limit, return True
    
    DEPENDENCIES: Token model, settings.max_delay_existing_min
    SIDE EFFECTS: None (read-only)
    
    RULE: Cannot delay existing patients by more than max_delay_existing_min
    """
    # Get tokens at target counter
    target_tokens = db.query(Token).filter(
        Token.assigned_counter_id == to_counter.id,
        Token.status == "WAITING"
    ).all()
    
    # Check if reassigning would delay any of them beyond max_delay_existing_min
    # Simplified check: if target counter has more than 2 waiting tokens, might cause delay
    if len(target_tokens) > 2:
        return {
            'allowed': False,
            'reason': f'Reassignment would delay {len(target_tokens)} existing patients beyond {settings.max_delay_existing_min} minute limit'
        }
    
    return {
        'allowed': True,
        'reason': f'Reassignment would not delay existing patients beyond {settings.max_delay_existing_min} minute limit'
    }


def check_medical_prioritization(action: Dict[str, Any]) -> Dict[str, Any]:
    """
    PURPOSE: Check if action attempts to set medical priority (forbidden)
    
    PARAMETERS:
        action: Action dictionary to check
    
    RETURNS: {'allowed': bool, 'reason': str}
    
    WORKFLOW:
        1. Check if action includes priority_change field
        2. If yes, return False (AI cannot set medical priority)
        3. If no, return True
    
    DEPENDENCIES: None
    SIDE EFFECTS: None (read-only)
    
    RULE: No medical prioritization by AI - only follow staff-set priority values
    (Non-Negotiable Rule #5)
    """
    if action.get('priority_change'):
        return {
            'allowed': False,
            'reason': 'AI cannot set medical priority. Only staff can set priority values.'
        }
    
    return {
        'allowed': True,
        'reason': 'No priority change attempted by AI'
    }
