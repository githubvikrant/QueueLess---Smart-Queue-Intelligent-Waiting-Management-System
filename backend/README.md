# QueueLess - Member 3: Queue Engine

Clinic queue ka poora foundation: database, token lifecycle (state machine), routes,
audit log, realtime Socket.IO, virtual demo clock, seed data, tests.

## Chalane ka tareeka (Windows)
    venv\Scripts\activate          (pehli baar: setup.bat chalao)
    pip install -r requirements.txt
    pytest                         # 48 tests pass hone chahiye
    python seed.py                 # (optional) demo data reload
    uvicorn app.main:app --reload --port 8000

Server start pe DB khali ho to CityCare demo data khud load ho jata hai.
- API docs:  http://localhost:8000/docs
- Team contract: docs/API_CONTRACT.md

## Structure
    app/core/        config, virtual clock, errors
    app/db/          engine (SQLite WAL, FK on), session
    app/models/      services, counters, counter_services, tokens, events
    app/services/    state_machine, lifecycle, snapshot, eta (plug-in hook), events, presenter, publisher
    app/api/routes/  queue, tokens, counters, demo
    app/seeding/     CityCare data (data.py) + seeder
    tests/           48 tests
