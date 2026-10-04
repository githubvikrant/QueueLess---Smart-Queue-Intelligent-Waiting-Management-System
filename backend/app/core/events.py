"""
Socket.IO event emitters for real-time updates.

This module defines the Socket.IO server instance and helper functions
to emit events to connected clients (frontend) when state changes occur.

PURPOSE: Provide real-time event broadcasting to frontend clients
DEPENDENCIES: python-socketio
SIDE EFFECTS: Emits Socket.IO events to all connected clients
"""

import socketio
from typing import Dict, Any, List

# Create Socket.IO server instance
# async_mode='asgi' for FastAPI integration
# cors_allowed_origins='*' allows all origins for prototype (configure for production)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')


async def emit_queue_updated(data: Dict[str, Any] = None):
    """
    PURPOSE: Emit queue update event when token status changes
    
    PARAMETERS:
        data: Optional dictionary with update details (e.g., token_id, new_status)
    
    WORKFLOW:
        1. Emit 'queue:updated' event to all connected clients
        2. Frontend will re-fetch /api/queue/ and refresh the queue board
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - Token status changes (WAITING -> CALLED -> IN_SERVICE -> COMPLETED)
        - New token is created
        - Token is reassigned to different counter
    """
    if data is None:
        data = {}
    await sio.emit('queue:updated', data)


async def emit_eta_updated(affected_token_ids: List[str], snapshots: Dict[str, Any] = None):
    """
    PURPOSE: Emit ETA update event when ETAs are recalculated
    
    PARAMETERS:
        affected_token_ids: List of token IDs whose ETAs changed
        snapshots: Optional dictionary with ETA snapshots before/after
    
    WORKFLOW:
        1. Emit 'eta:updated' event with affected token IDs
        2. Frontend will highlight affected tokens and re-fetch queue
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - ETA recalculation completes (eta_service.calculate_all_etas)
        - Service duration is updated
        - Counter status changes
        - Token is completed (affects all tokens behind it)
    """
    payload = {
        'affected_token_ids': affected_token_ids,
        'snapshots': snapshots or {}
    }
    await sio.emit('eta:updated', payload)


async def emit_recommendation_created(recommendation: Dict[str, Any]):
    """
    PURPOSE: Emit recommendation created event when AI agent proposes an action
    
    PARAMETERS:
        recommendation: Dictionary with recommendation details (id, type, reason, etc.)
    
    WORKFLOW:
        1. Emit 'recommendation:created' event with recommendation data
        2. Frontend will show new recommendation card in AgentPanel
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - LLM agent proposes a REASSIGN action
        - LLM agent proposes an OPEN_COUNTER action
        - LLM agent proposes a NOTIFY action
    """
    await sio.emit('recommendation:created', recommendation)


async def emit_recommendation_decided(recommendation_id: int, decision: str, reason: str = None):
    """
    PURPOSE: Emit recommendation decided event when recommendation is approved/rejected
    
    PARAMETERS:
        recommendation_id: ID of the recommendation that was decided
        decision: 'APPROVED' or 'REJECTED'
        reason: Optional reason for the decision
    
    WORKFLOW:
        1. Emit 'recommendation:decided' event with decision details
        2. Frontend will update recommendation status in AgentPanel
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - Receptionist approves a recommendation
        - Receptionist rejects a recommendation
    """
    payload = {
        'recommendation_id': recommendation_id,
        'decision': decision,
        'reason': reason
    }
    await sio.emit('recommendation:decided', payload)


async def emit_token_called(token_id: str, counter_name: str):
    """
    PURPOSE: Emit token called event when a patient is called to a counter
    
    PARAMETERS:
        token_id: ID of the token being called
        counter_name: Name of the counter (e.g., "Counter A")
    
    WORKFLOW:
        1. Emit 'token:called' event with token and counter info
        2. Frontend will show toast notification: "Token Q103 — please go to Counter B"
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - Queue engine calls the next token for a counter
        - Token status changes from WAITING to CALLED
    """
    payload = {
        'token_id': token_id,
        'counter_name': counter_name
    }
    await sio.emit('token:called', payload)


async def emit_token_no_show(token_id: str):
    """
    PURPOSE: Emit no-show event when a patient fails to respond to call
    
    PARAMETERS:
        token_id: ID of the token marked as no-show
    
    WORKFLOW:
        1. Emit 'token:no_show' event with token ID
        2. Frontend will update token status badge to NO_SHOW
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - No-show grace timer expires
        - Demo manually marks a token as no-show
    """
    payload = {
        'token_id': token_id
    }
    await sio.emit('token:no_show', payload)


async def emit_audit_entry(entry: Dict[str, Any]):
    """
    PURPOSE: Emit audit entry event when any event is logged
    
    PARAMETERS:
        entry: Dictionary with audit entry details (timestamp, event_type, actor, etc.)
    
    WORKFLOW:
        1. Emit 'audit:entry' event with audit entry data
        2. Frontend will append new entry to audit log timeline
    
    DEPENDENCIES: Socket.IO server instance (sio)
    SIDE EFFECTS: Broadcasts event to all connected Socket.IO clients
    
    USAGE:
        Called when:
        - Any event is logged to AuditEntry table
        - Bottleneck detected
        - Recommendation created/decided
        - Queue updated
        - Token status changed
    """
    await sio.emit('audit:entry', entry)
