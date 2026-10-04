# QueueLess — Member 2 Task Brief
## Role: Frontend — Receptionist Dashboard + Patient View
### Branch: `dashboard`

---

## What is QueueLess?

QueueLess is an AI-powered adaptive queue management system built for a hackathon.
The demo setting is CityCare Diagnostic Centre — a small clinic with 2 service counters and 12 patients.

The system:
- Shows a live queue board with real-time ETA updates
- Displays AI-generated recommendations to the receptionist (with Approve / Reject buttons)
- Lets the receptionist inject demo events (delays, walk-ins, no-shows)
- Shows a patient-facing view where a patient can look up their token and ETA
- Shows an audit log timeline of every event and decision

Your job is to build the FRONTEND — all 3 pages and all components.
The backend (Member 1) provides the REST API and Socket.IO events.
Member 3 may help with the what-if panel and supporting frontend work.

Stack: React + Vite + Vanilla CSS + Socket.IO client

---

## First Thing: Set Up Your Branch

git clone <repo-url>
cd QueueLess
git checkout -b dashboard

Your work lives entirely inside the frontend/ folder.

frontend/
|-- index.html
|-- vite.config.js
|-- package.json
|-- src/
|   |-- main.jsx                  App entry, router
|   |-- socket.js                 Socket.IO client singleton
|   |-- pages/
|   |   |-- Dashboard.jsx         Receptionist view (main page)
|   |   |-- PatientView.jsx       Patient token lookup
|   |   `-- AuditLog.jsx          Event timeline
|   |-- components/
|   |   |-- QueueBoard.jsx        Per-counter token list with ETAs
|   |   |-- TokenCard.jsx         Single token row
|   |   |-- AgentPanel.jsx        Recommendation cards + Approve/Reject
|   |   |-- WhatIfPanel.jsx       What-if simulator controls + comparison
|   |   |-- DemoControls.jsx      Inject delay / walk-ins / no-show / appointment
|   |   `-- NotificationToast.jsx In-UI simulated patient notification
|   `-- styles/
|       `-- index.css             All styles

---

## Setup

cd frontend
npm install
npm run dev
# App runs on http://localhost:3000
# Backend must be running on http://localhost:8000

package.json dependencies:
  react
  react-dom
  react-router-dom
  socket.io-client

devDependencies:
  @vitejs/plugin-react
  vite

vite.config.js proxy setup (important — add this so /api calls go to backend):
  server.proxy["/api"] = "http://localhost:8000"
  server.proxy["/socket.io"] = { target: "http://localhost:8000", ws: true }

---

## Backend API Reference

The backend (port 8000) provides these endpoints. Use fetch() to call them.

GET  /api/queue/                           all tokens (array)
GET  /api/queue/{token_id}                 single token + ETA info
POST /api/queue/checkin                    ?service=...&kind=WALK_IN    register new patient
POST /api/queue/demo/inject-delay          ?counter_id=A&extra_minutes=12
POST /api/queue/demo/add-walkins           ?count=5
POST /api/queue/demo/mark-noshow          ?token_id=Q104

GET  /api/counters/                        all counters
POST /api/counters/{id}/status             ?status=AVAILABLE

GET  /api/agent/recommendations            PENDING recommendations
POST /api/agent/recommendations/{id}/approve
POST /api/agent/recommendations/{id}/reject
POST /api/agent/chat                       ?message=...   send to LLM agent

POST /api/simulation/                      body: {extra_patients, extra_counters, service_delay_min}

GET  /api/notifications/audit              recent audit log entries

---

## Socket.IO Events to Listen To

Connect to Socket.IO at http://localhost:8000

Events the backend emits — subscribe to these and update UI:

  queue:updated             re-fetch /api/queue/ and refresh board
  eta:updated               data has affected_token_ids — highlight those tokens, re-fetch queue
  recommendation:created    re-fetch /api/agent/recommendations and show in AgentPanel
  recommendation:decided    update recommendation status in AgentPanel
  token:called              show a toast notification: "Token Q103 — please go to Counter B"
  token:no_show             update token status badge
  audit:entry               append to audit log list

Socket.IO client singleton (socket.js):
  import { io } from "socket.io-client"
  const socket = io("http://localhost:8000", { transports: ["websocket"] })
  export default socket

---

## Page 1: Dashboard.jsx (Receptionist View — main page, route: "/")

Layout (keep it simple — 2 columns):
  Left column:
    - QueueBoard component (the live queue per counter)
    - DemoControls component (buttons for demo events)
  Right column:
    - AgentPanel component (pending recommendations with Approve/Reject)
    - WhatIfPanel component (what-if simulator)

On mount:
  - fetch /api/queue/ and store tokens in state
  - fetch /api/counters/ and store counters in state
  - subscribe to queue:updated -> re-fetch tokens
  - subscribe to eta:updated -> highlight affected tokens, re-fetch tokens

---

## Component: QueueBoard.jsx

Props: tokens (array), counters (array), affectedIds (array of highlighted token IDs)

Display:
  - One section per counter (Counter A, Counter B)
  - Show counter status (BUSY/AVAILABLE) and what service it supports
  - List all tokens assigned to or eligible for that counter
  - Each token rendered via TokenCard
  - Tokens in affectedIds should be visually highlighted (different background or border)

---

## Component: TokenCard.jsx

Props: token (object), isAffected (bool)

Display per token row:
  - Token ID (Q101)
  - Service name (Blood Test)
  - Status badge: WAITING / CALLED / IN_SERVICE / COMPLETED / NO_SHOW
  - ETA: show eta_expected as time (e.g. "10:14") and the range as "~10:11 - 10:17"
  - If isAffected: highlight the row (e.g. yellow border) — means ETA just changed
  - If status is IN_SERVICE: show green
  - If status is NO_SHOW: show red

---

## Component: AgentPanel.jsx

Fetches PENDING recommendations from /api/agent/recommendations on mount.
Re-fetches when socket emits recommendation:created.

For each PENDING recommendation display a card:
  - Type: REASSIGN / OPEN_COUNTER / NOTIFY
  - Token ID + which counter it moves from/to
  - Wait before: X minutes (computed by backend, not invented)
  - Wait after: Y minutes (computed by backend, not invented)
  - Reason: plain text from LLM
  - [Approve] button -> POST /api/agent/recommendations/{id}/approve
  - [Reject] button  -> POST /api/agent/recommendations/{id}/reject
  - After decision: remove card from list

Also include a simple text input + send button to chat with the agent:
  POST /api/agent/chat with the message
  Show the agent's response below

---

## Component: DemoControls.jsx

Buttons to inject demo events (for the live hackathon demo):

  [Inject Delay] -> input for counter (A or B) + minutes -> POST /api/queue/demo/inject-delay
  [Add 5 Walk-ins] -> POST /api/queue/demo/add-walkins?count=5
  [Mark No-show] -> input for token ID -> POST /api/queue/demo/mark-noshow
  [Late Appointment] -> input for token ID -> simulates Q108 arriving late

After each action call onUpdate() prop to refresh the parent.

---

## Component: WhatIfPanel.jsx

Inputs:
  - Extra patients (number, default 0)
  - Extra counters (number, default 0)
  - Service delay minutes (number, default 0)
  [Run Simulation] button

On submit: POST /api/simulation/ with the inputs

Display result as a comparison table:

  | | Current Setup | Proposed Setup |
  |--|--|--|
  | Active counters | 2 | 3 |
  | Patients waiting | 11 | 11 |
  | Avg wait (min) | 34 | 21 |
  | Difference | | 13 min less per patient |

IMPORTANT: Always show a label "Simulation / Illustrative" next to the results.
This is required by the project rules. The results are NOT measured real-world data.

---

## Page 2: PatientView.jsx (route: "/patient")

Simple page. A patient types their token ID (e.g. Q103) and sees:
  - Their token ID
  - Which counter they are assigned to (or "Waiting to be assigned")
  - Service type
  - ETA range: "About 10 to 14 minutes"
  - Status badge
  - A short reason if ETA changed recently (token.eta_reason field)

On mount or when token:called / eta:updated socket events fire, refresh the token data.

---

## Page 3: AuditLog.jsx (route: "/audit")

Fetches from /api/notifications/audit on mount.
Updates when audit:entry socket event fires.

Display a table / timeline:
  | Time | Event Type | Actor | Detail |
  |------|-----------|-------|--------|
  | 10:10:00 | BOTTLENECK_DETECTED | SYSTEM | Counter A projected wait exceeded threshold |
  | 10:10:05 | RECOMMENDATION | AGENT | Reassign Q103 to Counter B. Before: 22 min, After: 8 min |
  | 10:10:12 | APPROVED | RECEPTIONIST | Recommendation #1 approved |
  | 10:10:13 | QUEUE_UPDATED | SYSTEM | Q103 moved to Counter B |

Newest entries at the top. Show up to last 50 entries.

---

## Design Notes (Minimal Prototype)

Keep the UI clean and functional, not fancy:
  - Dark background (#0f0f0f or similar), light text
  - Monospace font for token IDs and numbers
  - Color-coded status badges (green=in service, yellow=called, grey=waiting, red=no-show)
  - Clear table layout for queue board
  - Highlighted row when ETA changes (yellow border or background)
  - Approve button: green. Reject button: red.
  - Simulation results always labelled with "Simulation" tag

The goal is clarity for a judge watching a demo, not visual wow.

---

## Build Order

1. package.json + vite.config.js + index.html + main.jsx   (app boots, 3 routes work)
2. socket.js                                                (Socket.IO client connected)
3. styles/index.css                                         (basic dark layout)
4. QueueBoard + TokenCard                                   (show static token list from API)
5. Socket.IO integration                                    (live updates work)
6. DemoControls                                             (inject delay button works)
7. AgentPanel + Approve/Reject                              (recommendations show and respond)
8. PatientView                                              (token lookup works)
9. AuditLog                                                 (timeline shows)
10. WhatIfPanel                                             (simulation comparison shows)
11. NotificationToast                                       (token:called pop-up)

---

## Git Workflow

git checkout -b dashboard
git add .
git commit -m "feat: queue board with live ETA updates"
git push origin dashboard
# open Pull Request to main when a feature is complete
