"""
Agent API endpoints.

This module provides REST API endpoints for the LLM agent:
- Chat with agent
- Get pending recommendations
- Approve/reject recommendations

PURPOSE: Provide HTTP interface for AI agent operations
DEPENDENCIES: FastAPI, SQLAlchemy, app.services.agent_service, app.schemas, app.core.events
SIDE EFFECTS: Creates recommendations, updates database, emits socket events
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database.db import get_db
from app.database.models import Recommendation
from app.schemas.queue import AgentChatRequest, AgentChatResponse, RecommendationResponse
from app.services.agent_service import chat_with_agent, execute_approved_action, reject_recommendation
from app.core.events import emit_recommendation_decided

# Create API router
router = APIRouter()


@router.post("/chat", response_model=AgentChatResponse)
def chat_with_llm_agent(request: AgentChatRequest):
    """
    PURPOSE: Send a message to the LLM agent and get response
    
    PARAMETERS:
        request: AgentChatRequest with message
    
    RETURNS: AgentChatResponse with agent's response and any recommendations
    
    WORKFLOW:
        1. Call agent_service.chat_with_agent with the message
        2. Return agent's natural language response
        3. Include any recommendations created by the agent
    
    DEPENDENCIES: chat_with_agent
    SIDE EFFECTS: May create recommendations, emit socket events
    
    USAGE: Frontend calls this to chat with the AI agent
    """
    try:
        result = chat_with_agent(request.message)
        
        return AgentChatResponse(
            response=result['response'],
            recommendations=result.get('recommendations', [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@router.get("/recommendations", response_model=List[RecommendationResponse])
def get_pending_recommendations(db: Session = Depends(get_db)):
    """
    PURPOSE: Get all PENDING recommendations
    
    PARAMETERS:
        db: Database session (injected by FastAPI)
    
    RETURNS: List of RecommendationResponse objects with status=PENDING
    
    WORKFLOW:
        1. Query all recommendations with status=PENDING
        2. Include related token and counter details
        3. Return list ordered by created_at (newest first)
    
    DEPENDENCIES: Recommendation model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Frontend calls this to display pending recommendations in AgentPanel
    """
    recommendations = db.query(Recommendation).filter(
        Recommendation.status == "PENDING"
    ).order_by(Recommendation.created_at.desc()).all()
    
    result = []
    for rec in recommendations:
        # Get token details if exists
        token_info = None
        if rec.token:
            token_info = {
                'id': rec.token.id,
                'service_name': rec.token.service_type.name if rec.token.service_type else None
            }
        
        rec_dict = {
            'id': rec.id,
            'type': rec.type,
            'token_id': rec.token_id,
            'token': token_info,
            'from_counter_id': rec.from_counter_id,
            'to_counter_id': rec.to_counter_id,
            'wait_before_min': rec.wait_before_min,
            'wait_after_min': rec.wait_after_min,
            'reason': rec.reason,
            'status': rec.status,
            'created_at': rec.created_at,
            'decided_at': rec.decided_at
        }
        result.append(RecommendationResponse(**rec_dict))
    
    return result


@router.post("/recommendations/{recommendation_id}/approve")
def approve_recommendation(recommendation_id: int, db: Session = Depends(get_db)):
    """
    PURPOSE: Approve a recommendation and execute the action
    
    PARAMETERS:
        recommendation_id: ID of the recommendation to approve
        db: Database session (injected by FastAPI)
    
    RETURNS: Dictionary with approval result
    
    WORKFLOW:
        1. Call agent_service.execute_approved_action
        2. If successful, update recommendation status to APPROVED
        3. Emit recommendation:decided socket event
        4. Log to audit trail
        5. Return success message
    
    DEPENDENCIES: execute_approved_action, emit_recommendation_decided
    SIDE EFFECTS: Executes action, updates recommendation, emits events
    
    USAGE: Frontend calls this when receptionist clicks "Approve" button
    """
    result = execute_approved_action(recommendation_id, db)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    # Emit socket event
    emit_recommendation_decided(
        recommendation_id=recommendation_id,
        decision='APPROVED',
        reason=result.get('message', '')
    )
    
    return result


@router.post("/recommendations/{recommendation_id}/reject")
def reject_recommendation_endpoint(recommendation_id: int, db: Session = Depends(get_db)):
    """
    PURPOSE: Reject a recommendation (queue unchanged)
    
    PARAMETERS:
        recommendation_id: ID of the recommendation to reject
        db: Database session (injected by FastAPI)
    
    RETURNS: Dictionary with rejection result
    
    WORKFLOW:
        1. Call agent_service.reject_recommendation
        2. Update recommendation status to REJECTED
        3. Emit recommendation:decided socket event
        4. Log to audit trail
        5. Return success message
    
    DEPENDENCIES: reject_recommendation, emit_recommendation_decided
    SIDE EFFECTS: Updates recommendation status, emits events, queue unchanged
    
    USAGE: Frontend calls this when receptionist clicks "Reject" button
    (Non-Negotiable Rule #6: Rejection must work, queue unchanged)
    """
    result = reject_recommendation(recommendation_id, db)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    # Emit socket event
    emit_recommendation_decided(
        recommendation_id=recommendation_id,
        decision='REJECTED',
        reason='Rejected by receptionist'
    )
    
    return result
