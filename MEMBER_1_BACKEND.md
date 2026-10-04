# QueueLess — Member 1 Task Brief
## Role: Backend Core + AI Agent Brain
### Branch: `backend`

---

## What is QueueLess?

QueueLess is an AI-powered adaptive queue management system built for a hackathon.
The demo setting is CityCare Diagnostic Centre — a small clinic with 2 service counters and 12 patients.

The system does what a smart floor manager would do:
- Watches the live queue (who is waiting, how long, which counter is free)
- Detects problems (one counter overloaded, another idle)
- Recommends fixes with real before/after numbers
- Asks the receptionist to approve before doing anything
- Explains every decision in plain language
- Logs everything in an audit trail

Stack: FastAPI (Python) + SQLite + Socket.IO (real-time) + LLM API (tool calling)

---

## First Thing: Set Up Your Branch

git clone <repo-url>
cd QueueLess
git checkout -b backend

Your work lives entirely inside the backend/ folder.

backend/
|-- app/
|   |-- main.py                   FastAPI app entry point
|   |-- api/
|   |   |-- queue.py              Token CRUD + demo controls
|   |   |-- counters.py           Counter management
|   |   |-- agent.py              LLM agent + approve/reject
|   |   |-- notifications.py      Audit log endpoint
|   |   `-- simulation.py         What-if endpoint
|   |-- core/
|   |   |-- config.py             All policy thresholds (no hardcoding)
|   |   `-- events.py             Socket.IO event emitters
|   |-- services/
|   |   |-- queue_engine.py       Token lifecycle and ordering
|   |   |-- eta_service.py        [STAR] ETA calculation engine
|   |   |-- bottleneck_service.py [STAR] Bottleneck detection
|   |   |-- validator_service.py  [STAR] Policy and constraint rules
|   |   |-- simulator_service.py  What-if deep-copy simulation
|   |   |-- noshow_service.py     No-show grace timer
|   |   `-- agent_service.py      [STAR] LLM tool-calling loop
|   |-- database/
|   |   |-- db.py                 SQLite connection + get_db()
|   |   |-- models.py             SQLAlchemy ORM models
|   |   `-- seed.py               Seed CityCare demo data
|   `-- schemas/
|       `-- queue.py              Pydantic request/response schemas
|-- data/                         queueless.db lives here
|-- requirements.txt
`-- .env.example

---

## Setup

cd backend
pip install -r requirements.txt
cp .env.example .env              # add your LLM API key
python -m app.database.seed       # populate the SQLite DB
uvicorn app.main:socket_app --reload --port 8000

requirements.txt must include:
  fastapi
  uvicorn[standard]
  sqlalchemy
  python-socketio
  python-dotenv
  pydantic
  pydantic-settings
  openai               # or google-generativeai / anthropic
  httpx
  aiofiles

.env:
  LLM_API_KEY=your_key_here
  LLM_MODEL=gpt-4o
  DATABASE_URL=sqlite:///./data/queueless.db

---

## Database Models (SQLAlchemy — models.py)

Build 6 tables:

ServiceType: id, name (Blood Test / ECG / Consultation), avg_duration_min, spread_min, recent_durations (JSON list)

Counter: id (A/B), name, status (AVAILABLE/BUSY/CLOSED), supported_services (JSON list), current_token_id (FK), expected_free_at (DateTime)

Token: id (Q101..Q112), service, kind (WALK_IN/APPOINTMENT), appointment_time, priority_class (int, staff-set only),
       status (WAITING/CALLED/IN_SERVICE/COMPLETED/NO_SHOW), assigned_counter_id, created_at,
       called_at, eta_low, eta_expected, eta_high, eta_reason

Recommendation: id, type (REASSIGN/OPEN_COUNTER/NOTIFY), token_id, from_counter_id, to_counter_id,
                wait_before_min (Float, computed by CODE not LLM),
                wait_after_min (Float, computed by CODE not LLM),
                reason (LLM plain text), status (PENDING/APPROVED/REJECTED), created_at, decided_at

AuditEntry: id, timestamp, event_type, actor (SYSTEM/AGENT/RECEPTIONIST),
            input_data (JSON), prediction (JSON), recommendation_id (FK), decision, result (JSON)

Policy (use pydantic-settings in config.py, not a DB table):
  bottleneck_threshold_min = 15
  notify_change_threshold_min = 5
  appointment_grace_min = 10
  max_delay_existing_min = 8
  no_show_grace_min = 3
  actions_requiring_approval = ["REASSIGN", "OPEN_COUNTER"]

---

## Seed Data (seed.py) — CityCare 10:00 AM state

Service Types:
  Blood Test    | avg 6 min  | spread 1.5 min
  ECG           | avg 8 min  | spread 2.0 min
  Consultation  | avg 10 min | spread 2.5 min

Counters:
  Counter A | BUSY      | supports: Blood Test, Consultation | current: Q101 | free_at: 10:06
  Counter B | AVAILABLE | supports: Blood Test, ECG          | current: null | free_at: 10:00

12 Tokens:
  Q101 | Blood Test   | WALK_IN      | IN_SERVICE | Counter A  (being served)
  Q102 | Consultation | WALK_IN      | WAITING
  Q103 | Blood Test   | WALK_IN      | WAITING    (bottleneck demo token)
  Q104 | ECG          | WALK_IN      | WAITING    (no-show at 10:20 in demo)
  Q105 | Consultation | WALK_IN      | WAITING
  Q106 | Blood Test   | WALK_IN      | WAITING
  Q107 | ECG          | WALK_IN      | WAITING
  Q108 | Consultation | APPOINTMENT  | WAITING    appointment_time=10:10, arrives late at 10:15
  Q109 | Blood Test   | WALK_IN      | WAITING
  Q110 | ECG          | WALK_IN      | WAITING
  Q111 | Consultation | WALK_IN      | WAITING
  Q112 | Blood Test   | WALK_IN      | WAITING

---

## STAR Feature 1: ETA Engine (eta_service.py)

This is the foundation. Every feature depends on it. MUST BUILD FIRST.

Algorithm (pure deterministic code, no AI):

  for each counter:
      free_at = now + expected_remaining_time(current_token)

  for each waiting token, in queue order (priority_class DESC, created_at ASC):
      pick the eligible counter with the earliest free_at
      token.eta_expected = that counter's free_at
      that counter's free_at += expected_duration(token.service)

  eta_low  = eta_expected - K * spread
  eta_high = eta_expected + K * spread
  (spread = std deviation of recent durations for services ahead)
  K = 1.0 recommended starting value

Functions to build:
  calculate_all_etas(db)          recalculates all WAITING tokens, saves to DB, returns affected token IDs + ETA snapshots
  expected_duration(service, db)  returns rolling average from ServiceType.avg_duration_min
  find_affected_tokens(token_id, db)  returns all tokens behind a given token on the same counter queue

Done when: Changing one service duration live updates ETAs for all tokens behind it within 1-2 seconds.

---

## STAR Feature 2: Bottleneck Detector (bottleneck_service.py)

Pure code, no AI involved.

Steps:
  1. Compute projected queue wait per counter using ETA engine
  2. If any counter's projected wait > bottleneck_threshold_min: bottleneck detected
  3. Check if another counter is idle AND supports the affected service
  4. Generate candidate REASSIGN actions

Functions:
  find_bottlenecks(db)                  returns list of {overloaded_counter, idle_counter, affected_tokens, projected_waits}
  generate_candidate_actions(bottleneck, db)  returns list of candidate actions

---

## STAR Feature 3: Validator (validator_service.py)

The safety gate. Can veto ANY recommendation. Rules beat speed always.

Rule checks:
  1. Service compatibility: target counter must support the token's service
  2. Appointment grace: appointment token gets appointment_grace_min window
  3. FCFS: within same priority class, preserve arrival order
  4. Max extra delay: cannot delay existing patients by more than max_delay_existing_min
  5. No medical prioritization: never set priority, only follow staff-set values

Function:
  validate_action(action, db)  returns {"allowed": bool, "reason": str}
  The reason string is shown to the receptionist when blocked.

KEY DEMO MOMENT: Moving a Consultation token to Counter B (Blood Test + ECG only)
must return allowed=False with a plain English reason. This proves the system is safe.

---

## STAR Feature 4: LLM Agent (agent_service.py)

The AI brain. It calls tools, reads results, explains in plain English. It NEVER calculates.

Tools to define for the LLM (function calling):
  get_queue_state()               read tokens + counters from DB
  get_eta_forecast(token_id?)     call eta_service
  find_bottlenecks()              call bottleneck_service
  validate_action(action)         call validator_service
  simulate_action(action)         call simulator_service on deep copy
  propose_action(action)          create PENDING Recommendation in DB + emit socket event
  execute_approved_action(id)     apply APPROVED rec, recalculate ETAs, notify, log
  get_audit_log()                 return recent AuditEntry rows

System prompt must enforce:
  - "Never calculate ETAs yourself. Always call get_eta_forecast or find_bottlenecks first."
  - "Always call validate_action before propose_action."
  - "Use only the numbers returned by tools. Do not invent or adjust them."
  - "Explain recommendations in 1-2 plain sentences using actual tool-returned numbers."

Loop: User message -> LLM -> tool calls -> tool results -> LLM -> explanation + propose_action

---

## Feature 5: What-If Simulator (simulator_service.py)

  Input scenario: {extra_patients, extra_counters, service_delay_min}
  DEEP COPY the live queue state (NEVER touch the real DB)
  Apply scenario changes to the copy
  Run ETA engine on the copy
  Return: {current: {...}, proposed: {...}, difference: {...}, is_simulation: True}

  is_simulation: True MUST ALWAYS be in the return value. This is non-negotiable (Rule 8).

---

## Feature 6: No-Show Recovery (noshow_service.py)

  When token is CALLED: start async grace timer (no_show_grace_min from config)
  If patient does not respond in time: mark token NO_SHOW
  Recalculate ETAs for freed slot
  Offer slot to next eligible token
  Log to audit trail

---

## Socket.IO Events to Emit (core/events.py)

  queue:updated             any token status changes
  eta:updated               ETA recalc done, include affected_token_ids list
  recommendation:created    agent proposes action
  recommendation:decided    approve or reject received
  token:called              token called to counter
  token:no_show             no-show grace expired
  audit:entry               any audit log write

---

## API Endpoints to Build

api/queue.py:
  GET  /api/queue/                     all tokens ordered by queue position
  GET  /api/queue/{token_id}           single token + ETA
  POST /api/queue/checkin              register new patient, auto-generate token ID
  POST /api/queue/demo/inject-delay    add extra minutes to a counter (demo control)
  POST /api/queue/demo/add-walkins     add N walk-in patients (demo control)
  POST /api/queue/demo/mark-noshow     instantly mark a token NO_SHOW (demo control)

api/agent.py:
  POST /api/agent/chat                          natural language message to LLM agent
  GET  /api/agent/recommendations               list PENDING recommendations
  POST /api/agent/recommendations/{id}/approve  approve, execute, recalculate, log
  POST /api/agent/recommendations/{id}/reject   reject, log only, queue unchanged

api/counters.py:
  GET  /api/counters/            all counters
  POST /api/counters/{id}/status update counter status

api/simulation.py:
  POST /api/simulation/          run what-if scenario on copy of state

api/notifications.py:
  GET  /api/notifications/audit  recent audit log entries

---

## 10 Non-Negotiable Rules

1. LLM never does maths. ETAs, ranges, savings come from code. LLM only explains.
2. No invented numbers. Every before/after comes from a real calculation on live state.
3. Humans approve changes. Reassigning patients needs receptionist approval.
4. Rules beat speed. Validator can veto any recommendation, no exceptions.
5. No medical prioritization by AI. Only follow staff-set priority.
6. Rejection must work. Queue unchanged, rejection logged, app keeps running.
7. Everything is logged. Input, prediction, recommendation, decision, result -> audit log.
8. Simulations are labelled. What-if results always include is_simulation: true.
9. Thresholds are config. Nothing hardcoded — use config.py for all limits.
10. No external messaging required. In-UI notification simulation is enough.

---

## Build Order (do this sequence so teammates always have something to test)

1. models.py + db.py + seed.py         get DB running with 12 tokens
2. main.py + core/events.py            FastAPI + Socket.IO running on port 8000
3. eta_service.py                      core algorithm, test via /api/queue/
4. api/queue.py (GET endpoints)        let frontend see the queue
5. validator_service.py                test invalid reassignment rejection
6. bottleneck_service.py               detect Counter A overload scenario
7. api/agent.py approve/reject flow    test without LLM first
8. agent_service.py                    add LLM tool-calling on top
9. simulator_service.py                what-if deep copy
10. noshow_service.py                  if time remains

---

## Git Workflow

git checkout -b backend
# work and commit regularly
git add .
git commit -m "feat: ETA engine implementation"
git push origin backend
# open Pull Request to main when a feature is complete
