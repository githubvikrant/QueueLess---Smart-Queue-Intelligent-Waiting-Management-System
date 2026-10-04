"""
LLM Agent service - AI brain with tool-calling capability.

This is the STAR feature - the AI brain that calls tools, reads results,
and explains recommendations in plain language. It NEVER calculates.

PURPOSE: Provide AI-powered recommendations using LLM tool-calling
DEPENDENCIES: anthropic, SQLAlchemy, app.services, app.database.models, app.core.config
SIDE EFFECTS: Creates recommendations in database, emits socket events
"""

from anthropic import Anthropic
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.database.models import Token, Counter, Recommendation, AuditEntry
from app.database.db import SessionLocal
from app.core.config import settings
from app.services.eta_service import calculate_all_etas
from app.services.bottleneck_service import find_bottlenecks, generate_candidate_actions
from app.services.validator_service import validate_action
from app.services.queue_engine import log_audit_entry
from app.core.events import emit_recommendation_created, emit_audit_entry


# Initialize Anthropic client
# Uses API key from settings (loaded from .env file)
client = Anthropic(api_key=settings.llm_api_key)


def get_queue_state(db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Get current queue state (tokens and counters)
    
    PARAMETERS:
        db: Database session
    
    RETURNS: Dictionary with all tokens and counters
    
    WORKFLOW:
        1. Query all tokens with their service and counter info
        2. Query all counters with their status
        3. Return as structured dictionary
    
    DEPENDENCIES: Token, Counter models
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by LLM to understand current queue state
    """
    tokens = db.query(Token).all()
    counters = db.query(Counter).all()
    
    tokens_data = []
    for token in tokens:
        tokens_data.append({
            'id': token.id,
            'service': token.service_type.name,
            'kind': token.kind,
            'status': token.status,
            'assigned_counter': token.assigned_counter_id,
            'eta_expected': token.eta_expected.isoformat() if token.eta_expected else None,
            'priority_class': token.priority_class
        })
    
    counters_data = []
    for counter in counters:
        counters_data.append({
            'id': counter.id,
            'name': counter.name,
            'status': counter.status,
            'supported_services': counter.supported_services,
            'current_token': counter.current_token_id,
            'expected_free_at': counter.expected_free_at.isoformat() if counter.expected_free_at else None
        })
    
    return {
        'tokens': tokens_data,
        'counters': counters_data
    }


def get_eta_forecast(token_id: Optional[str] = None, db: Session = None) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Get ETA calculations for tokens
    
    PARAMETERS:
        token_id: Optional specific token ID (if None, returns all)
        db: Database session
    
    RETURNS: Dictionary with ETA information
    
    WORKFLOW:
        1. If token_id provided, get that specific token's ETA
        2. If no token_id, recalculate all ETAs and return snapshots
        3. Return structured ETA data
    
    DEPENDENCIES: calculate_all_etas, Token model
    SIDE EFFECTS: May recalculate ETAs if token_id is None
    
    USAGE: Called by LLM to get ETA predictions
    """
    if token_id:
        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            return {'error': f'Token {token_id} not found'}
        
        return {
            'token_id': token.id,
            'eta_low': token.eta_low.isoformat() if token.eta_low else None,
            'eta_expected': token.eta_expected.isoformat() if token.eta_expected else None,
            'eta_high': token.eta_high.isoformat() if token.eta_high else None,
            'eta_reason': token.eta_reason
        }
    else:
        # Recalculate all ETAs
        eta_result = calculate_all_etas(db)
        return eta_result


def find_bottlenecks_tool(db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Detect bottlenecks in the queue
    
    PARAMETERS:
        db: Database session
    
    RETURNS: Dictionary with bottleneck information
    
    WORKFLOW:
        1. Call bottleneck_service.find_bottlenecks
        2. Return bottleneck data with candidate actions
    
    DEPENDENCIES: find_bottlenecks, generate_candidate_actions
    SIDE EFFECTS: None (read-only detection)
    
    USAGE: Called by LLM to identify problems in the queue
    """
    bottlenecks = find_bottlenecks(db)
    
    if not bottlenecks:
        return {'bottlenecks': [], 'message': 'No bottlenecks detected'}
    
    # Generate candidate actions for each bottleneck
    for bottleneck in bottlenecks:
        candidates = generate_candidate_actions(bottleneck, db)
        bottleneck['candidate_actions'] = candidates
    
    return {'bottlenecks': bottlenecks}


def validate_action_tool(action: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Validate an action against policy rules
    
    PARAMETERS:
        action: Action dictionary to validate
        db: Database session
    
    RETURNS: Dictionary with validation result
    
    WORKFLOW:
        1. Call validator_service.validate_action
        2. Return allowed/rejected with reason
    
    DEPENDENCIES: validate_action
    SIDE EFFECTS: None (read-only validation)
    
    USAGE: Called by LLM before proposing any action
    """
    return validate_action(action, db)


def simulate_action(action: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Simulate an action on a deep copy of state
    
    PARAMETERS:
        action: Action dictionary to simulate
        db: Database session
    
    RETURNS: Dictionary with simulation results
    
    WORKFLOW:
        1. Call simulator_service.run_what_if
        2. Return simulation results with is_simulation=True
    
    DEPENDENCIES: simulator_service
    SIDE EFFECTS: None (simulation on copy only)
    
    USAGE: Called by LLM to test actions before proposing
    """
    from app.services.simulator_service import run_what_if
    
    # Create a simple scenario based on the action
    # For REASSIGN actions, we simulate with 0 extra patients/counters
    scenario = {
        'extra_patients': 0,
        'extra_counters': 0,
        'service_delay_min': 0
    }
    
    result = run_what_if(scenario, db)
    return result


def propose_action(action: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Create a PENDING recommendation in database
    
    PARAMETERS:
        action: Action dictionary with type, token_id, counters, wait times, reason
        db: Database session
    
    RETURNS: Dictionary with created recommendation ID
    
    WORKFLOW:
        1. Create Recommendation record with status=PENDING
        2. Save to database
        3. Emit recommendation:created socket event
        4. Log to audit trail
        5. Return recommendation ID
    
    DEPENDENCIES: Recommendation model, emit_recommendation_created
    SIDE EFFECTS: Creates recommendation, emits socket event, logs audit
    
    USAGE: Called by LLM after validation to propose an action
    """
    recommendation = Recommendation(
        type=action.get('type'),
        token_id=action.get('token_id'),
        from_counter_id=action.get('from_counter_id'),
        to_counter_id=action.get('to_counter_id'),
        wait_before_min=action.get('wait_before_min', 0),
        wait_after_min=action.get('wait_after_min', 0),
        reason=action.get('reason', ''),
        status='PENDING'
    )
    
    db.add(recommendation)
    db.commit()
    
    # Emit socket event
    emit_recommendation_created({
        'id': recommendation.id,
        'type': recommendation.type,
        'token_id': recommendation.token_id,
        'from_counter_id': recommendation.from_counter_id,
        'to_counter_id': recommendation.to_counter_id,
        'wait_before_min': recommendation.wait_before_min,
        'wait_after_min': recommendation.wait_after_min,
        'reason': recommendation.reason,
        'status': recommendation.status
    })
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="RECOMMENDATION_CREATED",
        actor="AGENT",
        input_data=action,
        recommendation_id=recommendation.id,
        result={'status': 'PENDING'}
    )
    
    return {
        'recommendation_id': recommendation.id,
        'status': 'PENDING'
    }


def get_audit_log_tool(db: Session, limit: int = 10) -> Dict[str, Any]:
    """
    PURPOSE: Tool for LLM - Get recent audit log entries
    
    PARAMETERS:
        db: Database session
        limit: Number of entries to return
    
    RETURNS: Dictionary with recent audit entries
    
    WORKFLOW:
        1. Query recent AuditEntry records
        2. Return as structured list
    
    DEPENDENCIES: AuditEntry model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Called by LLM to understand recent events
    """
    entries = db.query(AuditEntry).order_by(
        AuditEntry.timestamp.desc()
    ).limit(limit).all()
    
    entries_data = []
    for entry in entries:
        entries_data.append({
            'timestamp': entry.timestamp.isoformat(),
            'event_type': entry.event_type,
            'actor': entry.actor,
            'decision': entry.decision,
            'result': entry.result
        })
    
    return {'audit_entries': entries_data}


def chat_with_agent(message: str) -> Dict[str, Any]:
    """
    PURPOSE: Main function - Send message to LLM agent and get response
    
    PARAMETERS:
        message: Natural language message from user
    
    RETURNS: Dictionary with agent response and any recommendations
    
    WORKFLOW:
        1. Create database session
        2. Define system prompt with tool instructions
        3. Define available tools for LLM
        4. Call Anthropic API with message and tools
        5. Process tool calls if any
        6. Return agent's natural language response
    
    SYSTEM PROMPT RULES (Non-Negotiable):
        - Never calculate ETAs yourself - always call get_eta_forecast
        - Always call validate_action before propose_action
        - Use only numbers returned by tools - never invent
        - Explain in 1-2 plain sentences using actual tool numbers
    
    DEPENDENCIES: All tool functions, Anthropic client
    SIDE EFFECTS: May create recommendations, emit events
    
    USAGE: Called by api/agent.py chat endpoint
    """
    db = SessionLocal()
    
    try:
        # Define system prompt
        system_prompt = """You are QueueLess, an AI queue management assistant for a healthcare clinic.

Your role is to help the receptionist manage the queue by:
1. Detecting bottlenecks (overloaded counters)
2. Recommending fixes with real before/after numbers
3. Explaining decisions in plain language

CRITICAL RULES (never violate these):
1. NEVER calculate ETAs yourself. Always call get_eta_forecast or find_bottlenecks first.
2. ALWAYS call validate_action before propose_action.
3. Use ONLY the numbers returned by tools. Do not invent or adjust numbers.
4. Explain recommendations in 1-2 plain sentences using actual tool-returned numbers.
5. Rules beat speed - if validator rejects an action, explain why and stop.

Available tools:
- get_queue_state: Read current tokens and counters
- get_eta_forecast: Get ETA calculations (use before proposing actions)
- find_bottlenecks: Detect overloaded counters
- validate_action: Check if action violates policy rules
- simulate_action: Test action on copy of state (use before proposing)
- propose_action: Create PENDING recommendation after validation
- get_audit_log: See recent events

When the user asks for help:
1. First call get_queue_state to understand current situation
2. If asking about problems, call find_bottlenecks
3. If proposing an action, validate it first, then propose_action
4. Always explain using real numbers from tools.

Remember: You are an advisor, not a decision-maker. Humans approve operational changes."""

        # Define tools for Anthropic
        tools = [
            {
                "name": "get_queue_state",
                "description": "Get current queue state with all tokens and counters",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_eta_forecast",
                "description": "Get ETA calculations for tokens",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "token_id": {
                            "type": "string",
                            "description": "Optional specific token ID (if None, returns all)"
                        }
                    }
                }
            },
            {
                "name": "find_bottlenecks",
                "description": "Detect overloaded counters and get candidate actions",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "validate_action",
                "description": "Validate an action against policy rules",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "token_id": {"type": "string"},
                        "from_counter_id": {"type": "string"},
                        "to_counter_id": {"type": "string"}
                    },
                    "required": ["type"]
                }
            },
            {
                "name": "propose_action",
                "description": "Create a PENDING recommendation after validation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "token_id": {"type": "string"},
                        "from_counter_id": {"type": "string"},
                        "to_counter_id": {"type": "string"},
                        "wait_before_min": {"type": "number"},
                        "wait_after_min": {"type": "number"},
                        "reason": {"type": "string"}
                    },
                    "required": ["type", "reason", "wait_before_min", "wait_after_min"]
                }
            },
            {
                "name": "simulate_action",
                "description": "Simulate an action on a copy of state (what-if scenario)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "token_id": {"type": "string"},
                        "from_counter_id": {"type": "string"},
                        "to_counter_id": {"type": "string"}
                    },
                    "required": ["type"]
                }
            }
        ]
        
        # Helper function to execute tools
        def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
            """Execute a tool function and return result"""
            if tool_name == "get_queue_state":
                return get_queue_state(db)
            elif tool_name == "get_eta_forecast":
                token_id = tool_input.get("token_id")
                return get_eta_forecast(token_id, db)
            elif tool_name == "find_bottlenecks":
                return find_bottlenecks_tool(db)
            elif tool_name == "validate_action":
                return validate_action_tool(tool_input, db)
            elif tool_name == "simulate_action":
                return simulate_action(tool_input, db)
            elif tool_name == "propose_action":
                return propose_action(tool_input, db)
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        
        # Call Anthropic API
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": message}],
            tools=tools
        )
        
        # Process response
        agent_response = response.content[0].text
        
        # Check if LLM made tool calls
        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        
        recommendations = []
        
        # Execute tool calls if any
        for tool_use in tool_use_blocks:
            tool_result = execute_tool(tool_use.name, tool_use.input)
            
            # If tool was propose_action, get the recommendation
            if tool_use.name == "propose_action" and "recommendation_id" in tool_result:
                recommendations.append(tool_result)
        
        return {
            'response': agent_response,
            'recommendations': recommendations
        }
        
    finally:
        db.close()


def execute_approved_action(recommendation_id: int, db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Execute an approved recommendation
    
    PARAMETERS:
        recommendation_id: ID of the recommendation to execute
        db: Database session
    
    RETURNS: Dictionary with execution result
    
    WORKFLOW:
        1. Get the recommendation
        2. If not PENDING, return error
        3. Execute the action based on type
        4. Update recommendation status to APPROVED
        5. Recalculate ETAs
        6. Emit events
        7. Log to audit trail
        8. Return result
    
    DEPENDENCIES: queue_engine functions, calculate_all_etas
    SIDE EFFECTS: Modifies queue, recalculates ETAs, emits events
    
    USAGE: Called by api/agent.py approve endpoint
    """
    recommendation = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
    if not recommendation:
        return {'error': f'Recommendation {recommendation_id} not found'}
    
    if recommendation.status != 'PENDING':
        return {'error': f'Recommendation {recommendation_id} is not PENDING'}
    
    # Execute based on action type
    if recommendation.type == 'REASSIGN':
        from app.services.queue_engine import reassign_token
        result = reassign_token(recommendation.token_id, recommendation.to_counter_id, db)
        if result:
            recommendation.status = 'APPROVED'
            recommendation.decided_at = datetime.utcnow()
            db.commit()
            
            # Log to audit trail
            log_audit_entry(
                db=db,
                event_type="RECOMMENDATION_APPROVED",
                actor="RECEPTIONIST",
                input_data={'recommendation_id': recommendation_id},
                recommendation_id=recommendation_id,
                decision='APPROVED',
                result={'token_reassigned': True}
            )
            
            return {'success': True, 'message': f'Token {recommendation.token_id} reassigned to {recommendation.to_counter_id}'}
        else:
            return {'error': 'Failed to reassign token'}
    
    # Other action types can be added here
    
    return {'error': f'Action type {recommendation.type} not implemented yet'}


def reject_recommendation(recommendation_id: int, db: Session) -> Dict[str, Any]:
    """
    PURPOSE: Reject a recommendation
    
    PARAMETERS:
        recommendation_id: ID of the recommendation to reject
        db: Database session
    
    RETURNS: Dictionary with rejection result
    
    WORKFLOW:
        1. Get the recommendation
        2. Update status to REJECTED
        3. Set decided_at timestamp
        4. Log to audit trail
        5. Return result
    
    DEPENDENCIES: Recommendation model
    SIDE EFFECTS: Updates recommendation status, logs audit
    
    USAGE: Called by api/agent.py reject endpoint
    """
    recommendation = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
    if not recommendation:
        return {'error': f'Recommendation {recommendation_id} not found'}
    
    recommendation.status = 'REJECTED'
    recommendation.decided_at = datetime.utcnow()
    db.commit()
    
    # Log to audit trail
    log_audit_entry(
        db=db,
        event_type="RECOMMENDATION_REJECTED",
        actor="RECEPTIONIST",
        input_data={'recommendation_id': recommendation_id},
        recommendation_id=recommendation_id,
        decision='REJECTED',
        result={'queue_unchanged': True}
    )
    
    return {'success': True, 'message': f'Recommendation {recommendation_id} rejected'}
