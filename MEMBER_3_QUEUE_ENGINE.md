# QueueLess — Member 3 Task Brief
## Role: Queue Engine + API Routes + Seed Data + Frontend Support
### Branch: `queue-engine`

---

## What is QueueLess?

QueueLess is an AI-powered adaptive queue management system built for a hackathon.
The demo setting is CityCare Diagnostic Centre — a small clinic with 2 service counters and 12 patients.

The system:
- Manages a live queue of 12 patients across 2 service counters
- Automatically recalculates ETAs when anything changes
- Detects bottlenecks and recommends fixes (via AI agent in Member 1's code)
- Lets the receptionist approve or reject recommendations
- Simulates "what-if" scenarios without touching the live queue
- Logs every event in an audit trail

Your role bridges backend and frontend:
  - You implement the API route handlers (the HTTP interface the frontend calls)
  - You implement the token and counter lifecycle (queue_engine.py)
  - You write the seed data so the demo starts with the right 12 tokens
  - You support Member 2 with the WhatIfPanel and NotificationToast components

Stack: FastAPI (Python) + SQLite on the backend | React + Vite on frontend (support only)

---

## First Thing: Set Up Your Branch

git clone <repo-url>
cd QueueLess
git checkout -b queue-engine

Your primary work:
  backend/app/api/           all route files
  backend/app/services/queue_engine.py
  backend/app/database/seed.py
  backend/app/database/db.py
  backend/app/database/models.py    (coordinate with Member 1 on schema)
  backend/requirements.txt

Secondary (support Member 2 if needed):
  frontend/src/components/WhatIfPanel.jsx
  frontend/src/components/NotificationToast.jsx

---

## Setup

cd backend
pip install -r requirements.txt
cp .env.example .env
python -m app.database.seed        # loads CityCare demo data
uvicorn app.main:socket_app --reload --port 8000

---

## Your Primary Task: Seed Data (database/seed.py)

This is the most important thing you build first. The whole team depends on it.
Without the seed data, nothing can be demoed.

Write a script that:
  1. Drops and recreates all tables (init_db from db.py)
  2. Inserts the 3 service types
  3. Inserts the 2 counters
  4. Inserts the 12 tokens in the correct state
  5. Prints a confirmation message

The exact data to seed:

SERVICE TYPES:
  name=Blood Test   avg_duration_min=6.0  spread_min=1.5  recent_durations=[5.5, 6.0, 6.5, 5.8, 6.2]
  name=ECG          avg_duration_min=8.0  spread_min=2.0  recent_durations=[7.5, 8.0, 8.5, 7.8, 8.2]
  name=Consultation avg_duration_min=10.0 spread_min=2.5  recent_durations=[9.5,10.0,10.5, 9.8,10.2]

COUNTERS:
  id=A  name=Counter A  status=BUSY       supported_services=["Blood Test","Consultation"]
        current_token_id=Q101  expected_free_at=demo_start + 6 minutes

  id=B  name=Counter B  status=AVAILABLE  supported_services=["Blood Test","ECG"]
        current_token_id=null  expected_free_at=demo_start (now)

TOKENS (use demo_start = datetime of 10:00 AM for created_at offsets):
  Q101  Blood Test    WALK_IN      IN_SERVICE  assigned=A   (being served right now)
  Q102  Consultation  WALK_IN      WAITING
  Q103  Blood Test    WALK_IN      WAITING     (the bottleneck rescue demo token)
  Q104  ECG           WALK_IN      WAITING     (the no-show demo token — called at 10:20)
  Q105  Consultation  WALK_IN      WAITING
  Q106  Blood Test    WALK_IN      WAITING
  Q107  ECG           WALK_IN      WAITING
  Q108  Consultation  APPOINTMENT  WAITING     appointment_time=10:10, arrives late at 10:15
  Q109  Blood Test    WALK_IN      WAITING
  Q110  ECG           WALK_IN      WAITING
  Q111  Consultation  WALK_IN      WAITING
  Q112  Blood Test    WALK_IN      WAITING

Make the script re-runnable (clear data before inserting).
Run it with: python -m app.database.seed

---

## Your Primary Task: Database Connection (database/db.py)

Write db.py with:
  - SQLAlchemy engine pointing to sqlite:///./data/queueless.db
  - check_same_thread=False for SQLite
  - SessionLocal = sessionmaker(...)
  - init_db() function that calls Base.metadata.create_all(bind=engine)
  - get_db() generator function (FastAPI dependency) that yields a session and closes it

This file is used by every route and service. Get it right first.

---

## Your Primary Task: Queue Engine (services/queue_engine.py)

This manages token state transitions and queue ordering.

Functions to build:

get_ordered_queue(db)
  Returns all WAITING tokens ordered by:
    1. priority_class DESC (higher priority first — staff-set only)
    2. created_at ASC (first come, first served within same priority class)

call_next_token(counter_id, db)
  Finds the next WAITING token eligible for the given counter (check supported_services)
  Sets token status = CALLED
  Sets token.assigned_counter_id = counter_id
  Sets token.called_at = now
  Emits socket event token:called
  Starts the no-show grace timer (call noshow_service)

start_service(token_id, db)
  Sets token status = IN_SERVICE
  Sets counter.status = BUSY
  Emits socket event queue:updated

complete_service(token_id, actual_duration_min, db)
  Sets token status = COMPLETED
  Updates ServiceType.recent_durations (append actual_duration_min, keep last 10)
  Recalculates ServiceType.avg_duration_min as rolling average
  Sets counter.status = AVAILABLE, counter.current_token_id = null
  Calls eta_service.calculate_all_etas(db)   <- Member 1 builds this
  Emits eta:updated with affected token IDs
  Logs to AuditEntry

generate_token_id(db)
  Reads the highest existing token number (e.g. Q112 -> 112)
  Returns next ID as string (e.g. Q113)

---

## Your Primary Task: API Routes

Coordinate with Member 1 on service functions — you wire the routes, they build the services.
Import from app.services.* and call the right functions.

### api/queue.py

GET  /api/queue/
  Returns get_ordered_queue(db) as a list
  Include eta_low, eta_expected, eta_high, eta_reason fields in response

GET  /api/queue/{token_id}
  Returns single token or 404

POST /api/queue/checkin?service=Blood Test&kind=WALK_IN
  Generates next token ID using generate_token_id(db)
  Creates Token record with status=WAITING
  Calls eta_service.calculate_all_etas(db)
  Emits queue:updated
  Returns the new token

POST /api/queue/demo/inject-delay?counter_id=A&extra_minutes=12
  Updates counter.expected_free_at += extra_minutes
  Calls eta_service.calculate_all_etas(db)
  Emits eta:updated with list of affected token IDs
  Logs to AuditEntry: event_type=DELAY_INJECTED
  Returns {counter_id, new_free_at, affected_token_ids}

POST /api/queue/demo/add-walkins?count=5
  Creates count new tokens with random services (Blood Test, ECG, Consultation)
  Calls eta_service.calculate_all_etas(db)
  Emits queue:updated
  Returns list of new token IDs

POST /api/queue/demo/mark-noshow?token_id=Q104
  Immediately sets token.status = NO_SHOW (skips grace timer, for demo speed)
  Calls eta_service.calculate_all_etas(db)
  Emits token:no_show and eta:updated
  Logs to AuditEntry

### api/counters.py

GET  /api/counters/
  Returns all counters with current_token_id and expected_free_at

POST /api/counters/{counter_id}/status?status=AVAILABLE
  Updates counter.status
  Calls eta_service.calculate_all_etas(db)
  Emits queue:updated

### api/simulation.py

POST /api/simulation/
  Body: {extra_patients: 5, extra_counters: 1, service_delay_min: 0}
  Calls simulator_service.run_what_if(scenario, db)   <- Member 1 builds this
  Returns the result dict (which always includes is_simulation: true)

### api/notifications.py

GET  /api/notifications/audit?limit=50
  Returns recent AuditEntry rows, newest first

---

## FastAPI App Entry (app/main.py)

Build this so the whole app boots:

  Create FastAPI app
  Add CORS middleware (allow all origins for prototype)
  Mount Socket.IO using socketio.ASGIApp(sio, other_asgi_app=app)
  Include all routers with their prefixes
  Add startup event that calls init_db()

Run command: uvicorn app.main:socket_app --reload --port 8000

The Socket.IO server (sio) should be created in core/events.py and imported here.

---

## Core Config (core/config.py)

Build a pydantic-settings Settings class with these fields and defaults:

  llm_api_key: str = ""
  llm_model: str = "gpt-4o"
  database_url: str = "sqlite:///./data/queueless.db"
  bottleneck_threshold_min: int = 15
  notify_change_threshold_min: int = 5
  appointment_grace_min: int = 10
  max_delay_existing_min: int = 8
  no_show_grace_min: int = 3
  actions_requiring_approval: list = ["REASSIGN", "OPEN_COUNTER"]

  class Config:
      env_file = ".env"

  settings = Settings()

These are read from .env at startup and used everywhere. Nothing hardcoded in logic.

---

## requirements.txt

Write this file with exact versions or use latest:

  fastapi
  uvicorn[standard]
  sqlalchemy
  python-socketio
  python-dotenv
  pydantic
  pydantic-settings
  openai
  httpx
  aiofiles

---

## Secondary Task: Frontend Support

If Member 2 needs help, assist with these two components:

WhatIfPanel.jsx
  A panel with 3 inputs: extra patients, extra counters, service delay
  A "Run Simulation" button
  On click: POST /api/simulation/ with the inputs
  Show a comparison table:
    Current Setup vs Proposed Setup
    Rows: active counters, waiting patients, avg wait (min), difference
  Always show "Simulation / Illustrative" label next to the results

NotificationToast.jsx
  Listens to socket event token:called
  When fired: show a pop-up at bottom-right of screen
  Content: "Token {token_id} — Please proceed to {counter_name}"
  Auto-dismiss after 5 seconds

---

## Coordination Points

Talk to Member 1 before starting:
  - Agree on models.py schema (share the table definitions)
  - Agree on which services they build vs which you call
  - You call eta_service.calculate_all_etas(db) in your route handlers — make sure it is ready

Talk to Member 2:
  - Your API endpoints are what they fetch() — keep query param names consistent
  - Confirm the exact shape of the token JSON response (which fields they need)
  - Help them with WhatIfPanel if they are busy with other components

---

## Build Order

1. requirements.txt                             (so everyone can pip install)
2. database/db.py                               (init_db + get_db)
3. database/seed.py                             (12 tokens loaded in DB)
4. core/config.py                               (settings object)
5. core/events.py                               (Socket.IO sio instance + emit helpers)
6. app/main.py                                  (FastAPI boots, /docs works)
7. api/counters.py GET /api/counters/           (Member 2 can see counters)
8. api/queue.py GET /api/queue/                 (Member 2 can see tokens)
9. services/queue_engine.py                     (token lifecycle)
10. api/queue.py demo endpoints                 (inject-delay, add-walkins, mark-noshow)
11. api/simulation.py                           (when Member 1 finishes simulator_service)
12. api/notifications.py                        (audit log endpoint)
13. Frontend: WhatIfPanel + NotificationToast   (support Member 2)

---

## Git Workflow

git checkout -b queue-engine
git add .
git commit -m "feat: seed data + db connection working"
git push origin queue-engine
# open Pull Request to main when a feature is complete
