# QueueLess — Smart Queue & Intelligent Waiting Management System

> "A queue should reserve your turn, not imprison your time."

QueueLess is an AI-powered adaptive queue management system built for a hackathon.
It treats a queue as a living system — watching, predicting, recommending, and acting.

---

## What It Does

Most queue apps answer: "Who is next?"
QueueLess answers: "Given what is happening right now, what should we change to reduce waiting time, keep things fair, and keep the queue moving?"

- Live ETA updates with uncertainty ranges (not fake-precise single numbers)
- Bottleneck Rescue Agent — detects overloaded counters and recommends fixes
- Fairness-aware scheduling — rules beat speed, humans approve every operational change
- What-if simulator — test "open a third counter" without touching the live queue
- No-show recovery — grace timer, slot release, next eligible patient
- Full audit trail — every event, prediction, recommendation, and decision is logged

---

## Demo Setting: CityCare Diagnostic Centre

- 2 service counters (Counter A, Counter B)
- 12 registered patients (mix of walk-ins and appointments)
- 3 service types: Blood Test (6 min), ECG (8 min), Consultation (10 min)
- All data is synthetic — no real clinic data used

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite |
| Backend | FastAPI (Python) |
| Database | SQLite |
| Real-time | Socket.IO |
| AI Agent | LLM API with tool calling (OpenAI / Gemini / Anthropic) |

---

## Folder Structure

```
QueueLess/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/            queue, counters, agent, simulation, notifications
│   │   ├── core/           config (policy thresholds), events (Socket.IO)
│   │   ├── services/       eta_service, bottleneck_service, validator_service,
│   │   │                   agent_service, simulator_service, noshow_service
│   │   ├── database/       models, db, seed
│   │   └── schemas/
│   ├── data/               queueless.db (auto-created)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        ├── pages/          Dashboard, PatientView, AuditLog
        ├── components/     QueueBoard, AgentPanel, WhatIfPanel, DemoControls
        └── styles/
```

---

## Team & Branch Structure

```
main
├── backend        Member 1 — ETA engine, Bottleneck agent, Validator, LLM agent
├── dashboard      Member 2 — Receptionist dashboard, Patient view, Audit log
└── queue-engine   Member 3 — API routes, Queue lifecycle, Seed data, App wiring
```

Each member has a detailed task document in the repo root:

- MEMBER_1_BACKEND.md      — Backend core + AI agent brain
- MEMBER_2_FRONTEND.md     — Frontend (React pages + components)
- MEMBER_3_QUEUE_ENGINE.md — Queue engine + API routes + seed data

---

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # add LLM API key
python -m app.database.seed # load CityCare demo data
uvicorn app.main:socket_app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                 # runs on http://localhost:3000
```

---

## The 10 Non-Negotiable Rules

1. LLM never does maths — ETAs and savings come from code
2. No invented numbers — every before/after is a real calculation
3. Humans approve operational changes
4. Rules beat speed — validator can veto any recommendation
5. No medical prioritization by AI
6. Rejection must work — queue unchanged, rejection logged
7. Everything is logged — input, prediction, recommendation, decision, result
8. Simulations are labelled — what-if results always say "simulation"
9. Thresholds are configuration — nothing hardcoded
10. No external messaging required — in-UI notification is enough

---

## Track

Open Innovation / Everyday Automation
