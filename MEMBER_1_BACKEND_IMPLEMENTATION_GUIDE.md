# Member 1 Backend Implementation Guide
## Role: Backend Core + AI Agent Brain

This document provides a complete walkthrough of Member 1's backend implementation, including the step-by-step build process, decision-making rationale, function flow, and setup instructions.

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Build Process - Step by Step](#build-process---step-by-step)
4. [File-by-File Implementation Details](#file-by-file-implementation-details)
5. [Function Flow Diagrams](#function-flow-diagrams)
6. [LLM API Setup](#llm-api-setup)
7. [Testing Guide](#testing-guide)
8. [Integration with Member 3's Work](#integration-with-member-3s-work)

---

## Overview

### What Member 1 Builds
Member 1 is responsible for the **backend core + AI agent brain**. This includes:

**STAR Features (Core AI/Logic):**
1. ETA Engine - Calculates accurate ETAs with uncertainty ranges
2. Validator Service - Enforces policy rules (safety gate)
3. Bottleneck Detector - Identifies overloaded counters
4. LLM Agent - AI brain with tool-calling capability

**Additional Services:**
5. Simulator Service - What-if scenario testing
6. No-Show Service - Grace timer for patient no-shows

**API Endpoints:**
7. Agent API - LLM chat + recommendation management
8. Simulation API - What-if simulation endpoint

### What Member 3 Builds (For Reference)
Member 3 handles the foundational infrastructure:
- Database models, connection, and seed data
- Queue engine (token lifecycle)
- Basic API endpoints (queue, counters, notifications)

**Member 1's work depends on Member 3's foundation.**

---

## Architecture

### Layered Architecture
```
┌─────────────────────────────────────────┐
│         API Layer (Member 1)            │
│  - agent.py (LLM chat, recommendations)  │
│  - simulation.py (what-if scenarios)     │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│     Service Layer (Member 1 - STAR)     │
│  - eta_service.py (STAR)                │
│  - validator_service.py (STAR)          │
│  - bottleneck_service.py (STAR)         │
│  - agent_service.py (STAR - LLM)        │
│  - simulator_service.py                 │
│  - noshow_service.py                    │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│    Core Layer (Member 3 + Shared)       │
│  - config.py (policy thresholds)        │
│  - events.py (Socket.IO emitters)       │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│   Database Layer (Member 3)             │
│  - models.py (5 tables)                 │
│  - db.py (connection & session)         │
│  - seed.py (CityCare demo data)         │
└─────────────────────────────────────────┘
```

### Data Flow
```
User Request → API Endpoint → Service → Database → Socket.IO Event → Frontend
```

---

## Build Process - Step by Step

### Phase 1: Understanding Requirements

**First Step: Read the Documentation**
- Read `README.md` to understand the project
- Read `MEMBER_1_BACKEND.md` to understand specific tasks
- Read `MEMEMBER_3_QUEUE_ENGINE.md` to understand dependencies
- Read all three member docs to understand integration points

**Key Decisions Made:**
1. Use Anthropic Claude as LLM provider (user choice)
2. Build core features first, then add AI (user choice)
3. Use placeholder API key (user choice)

### Phase 2: Foundation Setup

**Step 1: Update Dependencies**
- File: `backend/requirements.txt`
- **Why:** Need Python 3.14 compatible versions
- **What Changed:** Updated to use `>=` instead of `==` for flexibility, added pydantic-settings, switched to anthropic
- **Next Thinking:** Need configuration management for policy thresholds

**Step 2: Create Configuration**
- File: `backend/app/core/config.py`
- **Why:** Centralize all policy thresholds (Non-Negotiable Rule #9: Nothing hardcoded)
- **What Added:**
  - `Settings` class with pydantic-settings
  - All policy thresholds (bottleneck_threshold_min, etc.)
  - LLM configuration (API key, model)
  - Database URL
- **Next Thinking:** Need database models to store data

### Phase 3: Service Layer - STAR Features

**Step 3: Build ETA Engine (STAR Feature #1)**
- File: `backend/app/services/eta_service.py`
- **Why:** Foundation - every other feature depends on accurate ETAs
- **Decision:** Build this first as everything uses it
- **Functions Added:**
  1. `expected_duration()` - Get rolling average from service
  2. `get_service_spread()` - Get uncertainty (std deviation)
  3. `calculate_counter_free_at()` - When counter is available
  4. `get_ordered_queue()` - Get tokens in queue order
  5. `is_counter_eligible()` - Check if counter can serve token
  6. `calculate_all_etas()` - Main ETA calculation algorithm
  7. `find_affected_tokens()` - Find tokens behind a given token

**Algorithm Thinking:**
- Pure deterministic code - no AI (Rule #1)
- For each counter: calculate free_at time
- For each waiting token (in queue order): assign to earliest eligible counter
- Calculate eta_low/expected/high using service spread
- K = 1.0 for uncertainty range

**Next Thinking:** Need to validate actions before executing them

**Step 4: Build Validator Service (STAR Feature #2)**
- File: `backend/app/services/validator_service.py`
- **Why:** Safety gate - can veto any recommendation (Rule #4: Rules beat speed)
- **Decision:** Build before AI agent so agent can use it
- **Functions Added:**
  1. `validate_action()` - Main validation function
  2. `check_service_compatibility()` - Counter supports service?
  3. `check_appointment_grace()` - Appointment within grace period?
  4. `check_fcfs_rule()` - Preserve arrival order?
  5. `check_max_delay()` - Not delaying existing patients too much?
  6. `check_medical_prioritization()` - AI not setting priority?

**Policy Rules Enforced:**
1. Service compatibility
2. Appointment grace period (appointment_grace_min)
3. FCFS (First-Come-First-Served)
4. Max delay for existing patients (max_delay_existing_min)
5. No medical prioritization by AI (Rule #5)

**Next Thinking:** Need to detect problems before agent can fix them

**Step 5: Build Bottleneck Detector (STAR Feature #3)**
- File: `backend/app/services/bottleneck_service.py`
- **Why:** Agent needs to know what problems exist
- **Decision:** Build before agent so agent can call it as a tool
- **Functions Added:**
  1. `find_bottlenecks()` - Detect overloaded counters
  2. `find_idle_counters()` - Find counters that can help
  3. `generate_candidate_actions()` - Generate REASSIGN actions
  4. `detect_single_bottleneck()` - Simplified version for agent

**Algorithm Thinking:**
- Use ETA engine to calculate projected waits
- If projected wait > bottleneck_threshold_min (15 min): bottleneck detected
- Find idle counters that support affected services
- Generate candidate REASSIGN actions with before/after wait times

**Next Thinking:** Now can build the AI agent that uses these tools

### Phase 4: AI Agent Implementation

**Step 6: Build LLM Agent Service (STAR Feature #4)**
- File: `backend/app/services/agent_service.py`
- **Why:** The AI brain that uses all the tools
- **Decision:** Build last as it depends on all other services
- **Functions Added:**
  1. `get_queue_state()` - Tool: Get current tokens and counters
  2. `get_eta_forecast()` - Tool: Get ETA calculations
  3. `find_bottlenecks_tool()` - Tool: Detect bottlenecks
  4. `validate_action_tool()` - Tool: Validate against policies
  5. `simulate_action()` - Tool: Test action on copy
  6. `propose_action()` - Tool: Create PENDING recommendation
  7. `get_audit_log_tool()` - Tool: See recent events
  8. `chat_with_agent()` - Main function: Send message to LLM
  9. `execute_approved_action()` - Execute approved recommendation
  10. `reject_recommendation()` - Reject recommendation

**LLM Integration Thinking:**
- Use Anthropic Claude with tool-calling
- System prompt enforces all 10 non-negotiable rules
- Agent NEVER calculates - only calls tools (Rule #1)
- Agent MUST validate before proposing (Rule #4)
- Agent uses only tool-returned numbers (Rule #2)

**Tool Design Rationale:**
- Each tool does one thing well
- Tools are pure functions (easy to test)
- Tools return structured data
- Tools have clear inputs/outputs

**Next Thinking:** Need simulation service for agent's simulate_action tool

### Phase 5: Additional Services

**Step 7: Build Simulator Service**
- File: `backend/app/services/simulator_service.py`
- **Why:** Agent needs to test actions before proposing
- **Decision:** Build so agent can use it as a tool
- **Functions Added:**
  1. `run_what_if()` - Main simulation function
  2. `calculate_queue_metrics()` - Calculate current metrics
  3. `estimate_proposed_metrics()` - Estimate proposed metrics
  4. `calculate_difference()` - Calculate difference

**Simulation Thinking:**
- Deep copy of state (never touch live DB)
- Apply scenario changes to copy
- Calculate metrics on copy
- Always return `is_simulation: True` (Rule #8)

**Next Thinking:** Need no-show handling for complete queue management

**Step 8: Build No-Show Service**
- File: `backend/app/services/noshow_service.py`
- **Why:** Handle patients who don't respond to calls
- **Decision:** Add for complete queue lifecycle
- **Functions Added:**
  1. `start_grace_timer()` - Start async grace timer
  2. `grace_timer_task()` - Async task that waits then marks no-show
  3. `cancel_grace_timer()` - Cancel timer if patient responds
  4. `mark_as_no_show()` - Mark token as no-show
  5. `get_active_grace_timers()` - Get active timers

**Grace Timer Thinking:**
- Async task waits for no_show_grace_min (3 min)
- If patient doesn't respond, mark as NO_SHOW
- Recalculate ETAs for freed slot
- Emit events for frontend update

### Phase 6: API Layer

**Step 9: Build Agent API**
- File: `backend/app/api/agent.py`
- **Why:** HTTP interface for agent operations
- **Decision:** Build after services so API can call them
- **Endpoints Added:**
  1. `POST /api/agent/chat` - Chat with LLM agent
  2. `GET /api/agent/recommendations` - Get PENDING recommendations
  3. `POST /api/agent/recommendations/{id}/approve` - Approve recommendation
  4. `POST /api/agent/recommendations/{id}/reject` - Reject recommendation

**API Design Thinking:**
- RESTful endpoints
- Pydantic schemas for validation
- Proper error handling
- Socket.IO events emitted for real-time updates

**Step 10: Build Simulation API**
- File: `backend/app/api/simulation.py`
- **Why:** HTTP interface for simulation
- **Decision:** Simple endpoint that calls simulator service
- **Endpoints Added:**
  1. `POST /api/simulation/` - Run what-if simulation

**Step 11: Update Main App**
- File: `backend/app/main.py`
- **Why:** Register new API routers
- **What Changed:** Added agent and simulation router imports and includes

### Phase 7: Integration and Refinement

**Step 12: Fix Import Dependencies**
- Fixed circular import issues
- Integrated simulator into agent's tool-calling
- Updated agent to use simulator_service

**Step 13: Add Pydantic Schemas**
- File: `backend/app/schemas/queue.py`
- **Why:** Request/response validation for API
- **What Added:** All schemas for tokens, counters, recommendations, audit, simulation

---

## File-by-File Implementation Details

### 1. `backend/requirements.txt`
**Purpose:** Define Python dependencies
**Key Changes:**
- Updated to Python 3.14 compatible versions
- Added `pydantic-settings` for configuration
- Switched from OpenAI to `anthropic`
- Used `>=` instead of `==` for flexibility

**Dependencies:**
- fastapi - Web framework
- uvicorn - ASGI server
- sqlalchemy - ORM
- python-socketio - Real-time events
- pydantic - Data validation
- pydantic-settings - Configuration management
- anthropic - LLM provider
- httpx - HTTP client
- aiofiles - Async file operations

### 2. `backend/app/core/config.py`
**Purpose:** Centralized configuration management
**Key Classes:**
- `Settings` - Pydantic settings class

**Configuration Fields:**
```python
llm_api_key: str = ""                    # Anthropic API key
llm_model: str = "claude-sonnet-4-20250514"  # Model to use
database_url: str = "sqlite:///./data/queueless.db"  # DB location

# Policy Thresholds (Rule #9: Nothing hardcoded)
bottleneck_threshold_min: int = 15       # Bottleneck detection threshold
notify_change_threshold_min: int = 5      # ETA change notification threshold
appointment_grace_min: int = 10          # Late appointment grace period
max_delay_existing_min: int = 8          # Max delay for existing patients
no_show_grace_min: int = 3               # No-show grace period

actions_requiring_approval: list = ["REASSIGN", "OPEN_COUNTER"]  # Actions needing approval
```

**Why This Design:**
- All thresholds in one place (easy to adjust)
- Loaded from .env file (separate from code)
- Type-safe with Pydantic validation
- Default values for development

### 3. `backend/app/services/eta_service.py`
**Purpose:** Calculate accurate ETAs with uncertainty ranges
**Key Functions:**

#### `expected_duration(service: ServiceType) -> float`
- **Purpose:** Get expected duration for a service
- **How:** Returns rolling average from ServiceType.avg_duration_min
- **Used by:** calculate_all_etas

#### `calculate_all_etas(db: Session) -> Dict[str, Any]`
- **Purpose:** Recalculate ETAs for all WAITING tokens
- **Algorithm:**
  1. Get current time
  2. Calculate when each counter will be free
  3. For each waiting token (in queue order):
     - Find earliest eligible counter
     - Set token's ETA to that counter's free_at
     - Add service duration to counter's free_at
     - Calculate eta_low = expected - K * spread
     - Calculate eta_high = expected + K * spread
  4. Save to database
  5. Return affected token IDs

**Why This Algorithm:**
- Deterministic (no AI, Rule #1)
- Fair (queue order respected)
- Accounts for uncertainty (spread)
- Updates all affected tokens

### 4. `backend/app/services/validator_service.py`
**Purpose:** Enforce policy rules (safety gate)
**Key Functions:**

#### `validate_action(action: Dict[str, Any], db: Session) -> Dict[str, Any]`
- **Purpose:** Validate a proposed action against all policy rules
- **Checks Performed:**
  1. Service compatibility (counter supports service?)
  2. Appointment grace (within grace period?)
  3. FCFS rule (preserve arrival order?)
  4. Max delay (not delaying existing patients too much?)
  5. Medical prioritization (AI not setting priority?)

**Why Each Check:**
- Service compatibility: Cannot assign to counter that doesn't support service
- Appointment grace: Appointments get grace period before being demoted
- FCFS: Preserve fairness within same priority
- Max delay: Don't make existing patients wait too long
- Medical prioritization: Only staff can set priority (Rule #5)

**Return Format:**
```python
{
    'allowed': bool,  # True if all checks pass
    'reason': str     # Explanation if blocked
}
```

### 5. `backend/app/services/bottleneck_service.py`
**Purpose:** Detect overloaded counters and generate fixes
**Key Functions:**

#### `find_bottlenecks(db: Session) -> List[Dict[str, Any]]`
- **Purpose:** Find all counters that are overloaded
- **Algorithm:**
  1. Recalculate ETAs using eta_service
  2. For each counter:
     - Get assigned waiting tokens
     - Calculate projected wait for last token
     - If wait > bottleneck_threshold_min: bottleneck detected
  3. For each bottleneck:
     - Find idle counters that can help
     - Identify affected tokens
  4. Return bottleneck list

**Bottleneck Definition:**
- Counter is bottleneck if projected wait > 15 minutes

#### `generate_candidate_actions(bottleneck: Dict[str, Any], db: Session) -> List[Dict[str, Any]]`
- **Purpose:** Generate candidate REASSIGN actions
- **Algorithm:**
  1. For each idle counter:
     - For each affected token that counter can serve:
       - Calculate wait before (from bottleneck)
       - Calculate wait after (assuming immediate service)
       - Calculate savings
       - Create candidate action
  2. Sort by savings (most impactful first)

**Candidate Action Format:**
```python
{
    'type': 'REASSIGN',
    'token_id': 'Q103',
    'from_counter_id': 'A',
    'to_counter_id': 'B',
    'wait_before_min': 22.5,
    'wait_after_min': 8.0,
    'savings_min': 14.5,
    'reason': 'Reassign Q103 from A to B, saving 14.5 minutes'
}
```

### 6. `backend/app/services/agent_service.py`
**Purpose:** LLM agent with tool-calling capability
**Key Functions:**

#### Tool Functions (6 tools for LLM)
1. `get_queue_state(db)` - Get current tokens and counters
2. `get_eta_forecast(token_id, db)` - Get ETA calculations
3. `find_bottlenecks_tool(db)` - Detect bottlenecks
4. `validate_action_tool(action, db)` - Validate action
5. `simulate_action(action, db)` - Test action on copy
6. `propose_action(action, db)` - Create PENDING recommendation

#### `chat_with_agent(message: str) -> Dict[str, Any]`
- **Purpose:** Main function - send message to LLM and get response
- **Workflow:**
  1. Create database session
  2. Define system prompt with rules
  3. Define available tools
  4. Call Anthropic API with message and tools
  5. Process tool calls if any
  6. Return agent's response

**System Prompt Rules:**
- Never calculate ETAs yourself - call get_eta_forecast
- Always validate before propose_action
- Use only tool-returned numbers - never invent
- Explain in 1-2 plain sentences
- Rules beat speed - if validator rejects, stop

**Why This Design:**
- LLM is advisor, not decision-maker
- Tools do the work, LLM explains
- Humans approve operational changes (Rule #3)

#### `execute_approved_action(recommendation_id: int, db: Session)`
- **Purpose:** Execute an approved recommendation
- **Workflow:**
  1. Get recommendation
  2. Check if PENDING
  3. Execute action based on type
  4. Update status to APPROVED
  5. Recalculate ETAs
  6. Emit events
  7. Log to audit trail

#### `reject_recommendation(recommendation_id: int, db: Session)`
- **Purpose:** Reject a recommendation (queue unchanged)
- **Workflow:**
  1. Get recommendation
  2. Update status to REJECTED
  3. Log to audit trail
  4. Queue unchanged (Rule #6)

### 7. `backend/app/services/simulator_service.py`
**Purpose:** What-if scenario testing on deep copy
**Key Functions:**

#### `run_what_if(scenario: Dict[str, Any], db: Session) -> Dict[str, Any]`
- **Purpose:** Run simulation on copy of state
- **Scenario Parameters:**
  - extra_patients: Number of additional patients
  - extra_counters: Number of additional counters
  - service_delay_min: Additional service delay

- **Workflow:**
  1. Get current state from database
  2. Create deep copy (NEVER touch live DB)
  3. Apply scenario changes to copy
  4. Calculate metrics on copy
  5. Return current, proposed, difference
  6. Always include `is_simulation: True` (Rule #8)

**Why Deep Copy:**
- Never modify live database
- Safe to test any scenario
- Frontend can see comparison

### 8. `backend/app/services/noshow_service.py`
**Purpose:** Handle patient no-shows with grace timer
**Key Functions:**

#### `start_grace_timer(token_id: str, db: Session)`
- **Purpose:** Start async grace timer for called token
- **Workflow:**
  1. Cancel existing timer if any
  2. Create async task to wait for grace period
  3. After grace period: mark as no-show
  4. Recalculate ETAs

#### `mark_as_no_show(token_id: str, db: Session)`
- **Purpose:** Mark token as no-show and handle recovery
- **Workflow:**
  1. Update status to NO_SHOW
  2. Clear assigned counter
  3. Recalculate ETAs
  4. Emit events
  5. Log to audit trail

**Grace Period:**
- Default: 3 minutes (configurable in config.py)
- If patient responds within grace: timer cancelled
- If patient doesn't respond: marked as no-show

### 9. `backend/app/api/agent.py`
**Purpose:** HTTP interface for agent operations
**Endpoints:**

#### `POST /api/agent/chat`
- **Purpose:** Chat with LLM agent
- **Request:** `{"message": "Help me with the queue"}`
- **Response:** Agent's response + any recommendations created

#### `GET /api/agent/recommendations`
- **Purpose:** Get all PENDING recommendations
- **Response:** List of recommendations with details

#### `POST /api/agent/recommendations/{id}/approve`
- **Purpose:** Approve and execute a recommendation
- **Workflow:** Calls agent_service.execute_approved_action

#### `POST /api/agent/recommendations/{id}/reject`
- **Purpose:** Reject a recommendation
- **Workflow:** Calls agent_service.reject_recommendation
- **Result:** Queue unchanged (Rule #6)

### 10. `backend/app/api/simulation.py`
**Purpose:** HTTP interface for simulation
**Endpoints:**

#### `POST /api/simulation/`
- **Purpose:** Run what-if simulation
- **Request:** `{"extra_patients": 5, "extra_counters": 1, "service_delay_min": 0}`
- **Response:** Current, proposed, difference metrics
- **Always includes:** `is_simulation: True` (Rule #8)

### 11. `backend/app/schemas/queue.py`
**Purpose:** Pydantic schemas for request/response validation
**Key Schemas:**
- `TokenResponse` - Token data with ETA info
- `CounterResponse` - Counter data with status
- `RecommendationResponse` - Recommendation with approval status
- `AuditEntryResponse` - Audit log entry
- `SimulationRequest/Response` - Simulation parameters and results
- `AgentChatRequest/Response` - Agent chat messages

---

## Function Flow Diagrams

### ETA Calculation Flow
```
Token Status Change
    ↓
calculate_all_etas() called
    ↓
Get all counters
    ↓
Calculate counter free_at times
    ↓
Get ordered queue (priority DESC, created_at ASC)
    ↓
For each token in queue:
    ↓
Find earliest eligible counter
    ↓
Set token.eta_expected = counter.free_at
    ↓
Add service duration to counter.free_at
    ↓
Calculate eta_low = expected - K * spread
    ↓
Calculate eta_high = expected + K * spread
    ↓
Update database
    ↓
Emit eta:updated event
```

### Agent Recommendation Flow
```
User sends message to agent
    ↓
chat_with_agent() called
    ↓
Anthropic API called with message + tools
    ↓
LLM calls tools:
    ↓
get_queue_state() → Returns current state
    ↓
find_bottlenecks_tool() → Returns bottlenecks
    ↓
validate_action_tool() → Checks policy rules
    ↓
propose_action() → Creates PENDING recommendation
    ↓
LLM explains in plain language
    ↓
Return response to user
    ↓
Frontend shows recommendation with Approve/Reject buttons
```

### Recommendation Approval Flow
```
User clicks Approve
    ↓
POST /api/agent/recommendations/{id}/approve
    ↓
execute_approved_action() called
    ↓
Get recommendation from DB
    ↓
Execute action (e.g., reassign token)
    ↓
Update recommendation status to APPROVED
    ↓
Recalculate ETAs
    ↓
Emit events (recommendation:decided, eta:updated)
    ↓
Log to audit trail
    ↓
Return success message
```

### Simulation Flow
```
User configures scenario
    ↓
POST /api/simulation/
    ↓
run_what_if() called
    ↓
Get current state from DB
    ↓
Create deep copy
    ↓
Apply scenario changes to copy
    ↓
Calculate metrics on copy
    ↓
Calculate difference
    ↓
Return current, proposed, difference
    ↓
Always includes is_simulation: True
```

---

## LLM API Setup

### Getting an Anthropic API Key

1. **Sign up for Anthropic:**
   - Go to https://console.anthropic.com/
   - Create an account
   - Verify your email

2. **Generate API Key:**
   - Navigate to API Keys section
   - Click "Create Key"
   - Give it a name (e.g., "QueueLess Backend")
   - Copy the API key (starts with `sk-ant-...`)

3. **Add API Key to Project:**
   - Create file: `backend/.env`
   - Add your API key:
   ```
   LLM_API_KEY=sk-ant-your-actual-api-key-here
   LLM_MODEL=claude-sonnet-4-20250514
   DATABASE_URL=sqlite:///./data/queueless.db
   ```

### Important Notes

**Single Place for API Key:**
- **YES** - You only need to add the API key in ONE place: `backend/.env`
- The `config.py` file reads from `.env` automatically
- All services use `settings.llm_api_key` from config
- No need to add API key anywhere else

**Security:**
- Never commit `.env` file to git (it's in .gitignore)
- Use `.env.example` as template (already exists)
- Keep your API key secret

**Model Selection:**
- Default: `claude-sonnet-4-20250514` (Sonnet 4)
- Alternative: `claude-3-5-sonnet-20241022` (Sonnet 3.5)
- For faster/cheaper: `claude-3-haiku-20240307` (Haiku)

**Testing Without API Key:**
- The backend will start without an API key
- Agent chat will fail with API error
- Other features (ETA, validator, bottleneck) work fine
- Get API key to test agent features

---

## Testing Guide

### 1. Start the Backend

```bash
cd backend
pip install -r requirements.txt
python -c "from app.database.seed import seed_database; seed_database()"
uvicorn app.main:socket_app --reload --port 8000
```

### 2. Test API Documentation

Visit: http://localhost:8000/docs

This shows all available endpoints with interactive testing.

### 3. Test Basic Features (No API Key Needed)

**Test Queue API:**
```bash
curl http://localhost:8000/api/queue/
```

**Test Counters API:**
```bash
curl http://localhost:8000/api/counters/
```

**Test Check-in:**
```bash
curl -X POST "http://localhost:8000/api/queue/checkin?service=Blood Test&kind=WALK_IN"
```

### 4. Test Agent Features (Requires API Key)

**Test Agent Chat:**
```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current queue status?"}'
```

**Test Get Recommendations:**
```bash
curl http://localhost:8000/api/agent/recommendations
```

### 5. Test Simulation

```bash
curl -X POST http://localhost:8000/api/simulation/ \
  -H "Content-Type: application/json" \
  -d '{"extra_patients": 5, "extra_counters": 1, "service_delay_min": 0}'
```

### 6. Test Demo Controls

**Inject Delay:**
```bash
curl -X POST "http://localhost:8000/api/queue/demo/inject-delay?counter_id=A&extra_minutes=10"
```

**Add Walk-ins:**
```bash
curl -X POST "http://localhost:8000/api/queue/demo/add-walkins?count=3"
```

**Mark No-show:**
```bash
curl -X POST "http://localhost:8000/api/queue/demo/mark-noshow?token_id=Q104"
```

---

## Integration with Member 3's Work

### Member 3 Provides (You Depend On):

1. **Database Models** (`database/models.py`)
   - ServiceType, Counter, Token, Recommendation, AuditEntry
   - Your services query these models

2. **Database Connection** (`database/db.py`)
   - `get_db()` dependency injection
   - Your services use this for database sessions

3. **Seed Data** (`database/seed.py`)
   - CityCare demo data (12 tokens, 2 counters)
   - Provides test data for your features

4. **Queue Engine** (`services/queue_engine.py`)
   - Token lifecycle functions
   - Your agent uses these to execute actions

5. **Basic APIs** (`api/queue.py`, `api/counters.py`, `api/notifications.py`)
   - Queue management endpoints
   - Frontend uses these alongside your agent API

6. **Core Infrastructure** (`core/config.py`, `core/events.py`)
   - Configuration management
   - Socket.IO event emitters
   - Your services emit these events

### Your Services Use Member 3's Code:

```python
# Your services import from Member 3's code
from app.database.models import Token, Counter, ServiceType
from app.database.db import get_db, SessionLocal
from app.core.config import settings
from app.core.events import emit_queue_updated, emit_eta_updated
from app.services.queue_engine import reassign_token, log_audit_entry
```

### No Conflicts:

- Member 3 built foundational infrastructure
- Member 1 (you) built AI/logic layer on top
- Clear separation of concerns
- No overlapping files
- Clean integration points

---

## Summary of Build Process

### Decision-Making Rationale

**Why Build in This Order?**

1. **Foundation First:** Config → Models → Database
   - Need configuration before anything else
   - Need database to store data
   - Member 3 provides this foundation

2. **Core Services Before AI:** ETA → Validator → Bottleneck
   - ETA is foundation for everything
   - Validator ensures safety
   - Bottleneck detection finds problems
   - AI needs these tools to work

3. **AI Last:** Agent depends on all other services
   - Agent calls ETA, Validator, Bottleneck as tools
   - Agent needs Simulator to test actions
   - Agent needs No-Show for complete lifecycle

4. **API After Services:** Services → API
   - Services contain business logic
   - API provides HTTP interface
   - Clean separation

### Key Design Decisions

1. **Pure Deterministic ETA:** No AI in calculations (Rule #1)
2. **Validator as Safety Gate:** Can veto any action (Rule #4)
3. **LLM as Advisor Only:** Never calculates, only explains
4. **Deep Copy Simulation:** Never touch live DB (Rule #8)
5. **Configuration-Driven:** All thresholds in config (Rule #9)
6. **Tool-Based AI:** LLM calls tools, doesn't do math
7. **Human Approval:** All operational changes need approval (Rule #3)

### Non-Negotiable Rules Compliance

✅ Rule #1: LLM never does maths - ETA service handles calculations
✅ Rule #2: No invented numbers - All from tool results
✅ Rule #3: Humans approve changes - Approve/reject endpoints
✅ Rule #4: Rules beat speed - Validator can veto
✅ Rule #5: No medical prioritization - Only staff-set priority
✅ Rule #6: Rejection must work - Queue unchanged, logged
✅ Rule #7: Everything logged - AuditEntry on every event
✅ Rule #8: Simulations labelled - is_simulation: True always
✅ Rule #9: Thresholds configurable - All in config.py
✅ Rule #10: No external messaging - Socket.IO in-UI only

---

## File Structure Summary

```
backend/
├── requirements.txt                    ✅ Dependencies
├── .env.example                       ✅ API key template
├── .env                               ⚠️  Add your API key here
├── app/
│   ├── main.py                        ✅ FastAPI app with routers
│   ├── core/
│   │   ├── config.py                  ✅ Configuration (Member 3 + shared)
│   │   └── events.py                  ✅ Socket.IO events (Member 3 + shared)
│   ├── database/
│   │   ├── db.py                      ✅ DB connection (Member 3)
│   │   ├── models.py                  ✅ ORM models (Member 3)
│   │   └── seed.py                    ✅ Demo data (Member 3)
│   ├── schemas/
│   │   └── queue.py                   ✅ Pydantic schemas
│   ├── services/
│   │   ├── eta_service.py             ✅ STAR - ETA calculation
│   │   ├── validator_service.py        ✅ STAR - Policy rules
│   │   ├── bottleneck_service.py      ✅ STAR - Bottleneck detection
│   │   ├── agent_service.py           ✅ STAR - LLM agent
│   │   ├── simulator_service.py       ✅ What-if simulation
│   │   ├── noshow_service.py          ✅ Grace timer
│   │   └── queue_engine.py            ✅ Token lifecycle (Member 3)
│   └── api/
│       ├── queue.py                   ✅ Queue API (Member 3)
│       ├── counters.py                ✅ Counters API (Member 3)
│       ├── notifications.py           ✅ Audit API (Member 3)
│       ├── agent.py                   ✅ Agent API (Member 1)
│       └── simulation.py              ✅ Simulation API (Member 1)
└── data/
    └── queueless.db                   📁 Created by seed.py
```

---

## Quick Reference

### Member 1 Files Created
- `backend/app/services/eta_service.py`
- `backend/app/services/validator_service.py`
- `backend/app/services/bottleneck_service.py`
- `backend/app/services/agent_service.py`
- `backend/app/services/simulator_service.py`
- `backend/app/services/noshow_service.py`
- `backend/app/api/agent.py`
- `backend/app/api/simulation.py`
- `backend/app/schemas/queue.py`

### Member 1 Functions (Key Ones)
- `calculate_all_etas()` - ETA calculation
- `validate_action()` - Policy validation
- `find_bottlenecks()` - Bottleneck detection
- `chat_with_agent()` - LLM agent chat
- `execute_approved_action()` - Execute recommendation
- `run_what_if()` - Simulation

### Member 1 API Endpoints
- `POST /api/agent/chat`
- `GET /api/agent/recommendations`
- `POST /api/agent/recommendations/{id}/approve`
- `POST /api/agent/recommendations/{id}/reject`
- `POST /api/simulation/`

---

## Conclusion

Member 1's backend implementation is complete. All STAR features (ETA, Validator, Bottleneck, Agent) are implemented with comprehensive comments explaining the workflow. The AI agent uses tool-calling with Anthropic Claude, enforcing all 10 non-negotiable rules. The backend is ready for integration with the frontend and testing.

**Next Steps:**
1. Add Anthropic API key to `backend/.env`
2. Seed the database
3. Start the server
4. Test the API endpoints
5. Integrate with frontend
