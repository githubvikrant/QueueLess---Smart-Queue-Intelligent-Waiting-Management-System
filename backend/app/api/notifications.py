"""
Notifications API endpoints.

This module provides REST API endpoints for audit log access:
- Get recent audit log entries

PURPOSE: Provide HTTP interface for audit trail access
DEPENDENCIES: FastAPI, SQLAlchemy, app.database.models, app.schemas
SIDE EFFECTS: None (read-only)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.database.db import get_db
from app.database.models import AuditEntry
from app.schemas.queue import AuditEntryResponse

# Create API router
router = APIRouter()


@router.get("/audit", response_model=List[AuditEntryResponse])
def get_audit_log(
    limit: int = Query(default=50, ge=1, le=100, description="Number of entries to return"),
    db: Session = Depends(get_db)
):
    """
    PURPOSE: Get recent audit log entries
    
    PARAMETERS:
        limit: Number of entries to return (default: 50, max: 100)
        db: Database session (injected by FastAPI)
    
    RETURNS: List of AuditEntryResponse objects, newest first
    
    WORKFLOW:
        1. Query audit entries ordered by timestamp descending
        2. Limit to specified number of entries
        3. Return list with all event details
    
    DEPENDENCIES: AuditEntry model
    SIDE EFFECTS: None (read-only)
    
    USAGE: Frontend calls this to display audit log timeline
    """
    entries = db.query(AuditEntry).order_by(
        AuditEntry.timestamp.desc()
    ).limit(limit).all()
    
    result = []
    for entry in entries:
        entry_dict = {
            'id': entry.id,
            'timestamp': entry.timestamp,
            'event_type': entry.event_type,
            'actor': entry.actor,
            'input_data': entry.input_data,
            'prediction': entry.prediction,
            'recommendation_id': entry.recommendation_id,
            'decision': entry.decision,
            'result': entry.result
        }
        result.append(AuditEntryResponse(**entry_dict))
    
    return result
