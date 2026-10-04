"""
Simulation API endpoints.

This module provides REST API endpoints for what-if simulations:
- Run what-if scenario on copy of state

PURPOSE: Provide HTTP interface for simulation operations
DEPENDENCIES: FastAPI, SQLAlchemy, app.services.simulator_service, app.schemas
SIDE EFFECTS: None (simulation on copy only - never touches live database)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.schemas.queue import SimulationRequest, SimulationResponse
from app.services.simulator_service import run_what_if

# Create API router
router = APIRouter()


@router.post("/", response_model=SimulationResponse)
def run_simulation(request: SimulationRequest, db: Session = Depends(get_db)):
    """
    PURPOSE: Run a what-if simulation on a deep copy of queue state
    
    PARAMETERS:
        request: SimulationRequest with scenario parameters
                  - extra_patients: Number of additional patients
                  - extra_counters: Number of additional counters
                  - service_delay_min: Additional service delay
        db: Database session (injected by FastAPI)
    
    RETURNS: SimulationResponse with current, proposed, and difference metrics
                 Always includes is_simulation: True
    
    WORKFLOW:
        1. Convert request to scenario dictionary
        2. Call simulator_service.run_what_if
        3. Return simulation results
    
    DEPENDENCIES: run_what_if
    SIDE EFFECTS: None (simulation on copy only)
    
    USAGE: Frontend calls this to test "what-if" scenarios
    (Non-Negotiable Rule #8: Simulations are labelled)
    """
    scenario = {
        'extra_patients': request.extra_patients,
        'extra_counters': request.extra_counters,
        'service_delay_min': request.service_delay_min
    }
    
    result = run_what_if(scenario, db)
    
    return SimulationResponse(
        current=result['current'],
        proposed=result['proposed'],
        difference=result['difference'],
        is_simulation=result['is_simulation']
    )
