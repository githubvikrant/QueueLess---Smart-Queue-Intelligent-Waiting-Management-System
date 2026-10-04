# QueueLess API Contract (Member 3 -> Member 1 & Member 2)

Base URL: http://localhost:8000   |   Live docs: http://localhost:8000/docs
Realtime: Socket.IO on the same server (http://localhost:8000)

## Errors (sab routes ka ek format)
    { "error": "not_eligible", "message": "Counter B does not offer General Consultation" }
404 not_found | 409 invalid_transition / counter_unavailable / conflict / concurrent_update |
422 not_eligible / no_counter_available / validation errors

## Member 2 (Frontend) - routes
| Method | Path | Kaam |
|---|---|---|
| GET | /api/queue | Poora board: counters + tokens (ETA range, position, reason) + stats |
| GET | /api/tokens/{code} | Patient view (Q103) |
| POST | /api/tokens | Join. Body: patient_name, service_code, phone?, priority?, is_walk_in? |
| POST | /api/tokens/{code}/call, /start, /complete, /no-show, /skip, /recall | Lifecycle |
| POST | /api/counters/{code}/call-next | Counter ki line ka agla token |
| POST | /api/counters/{code}/open, /close | Counter open/close (close pe tokens auto-shift) |
| POST | /api/counters | Naya counter (Counter C). Body: code, name, services[], is_open? |
| GET | /api/events?limit=&correlation_id= | Audit log timeline |
| POST | /api/demo/inject-delay | {counter_code, minutes} |
| POST | /api/demo/walk-ins | {count} |
| POST | /api/demo/advance-clock | {minutes} |
| POST | /api/demo/reset | Demo starting state pe wapas |

Service codes: blood_test, ecg, consultation. Counters: A (sab), B (blood_test, ecg).
Token statuses: waiting, called, in_service, completed, no_show, skipped.

### Token JSON
    {
      "code": "Q103", "patient_name": "Meera Iyer",
      "service_code": "blood_test", "service_name": "Blood Test",
      "counter_code": "A", "status": "waiting", "priority": 0, "is_walk_in": false,
      "position": 1, "eta_minutes": 22.0, "eta_min": 19, "eta_max": 29,
      "eta_text": "about 19-29 minutes",
      "last_change_reason": "Counter A is running 12 min behind",
      "created_at": "...", "called_at": null, "started_at": null, "completed_at": null
    }

### Socket.IO events (server -> client)
| Event | Payload | Use |
|---|---|---|
| queue:updated | {correlation_id, reason, queue: <GET /api/queue>} | Board refresh |
| eta:updated | {correlation_id, reason, changed: ["Q103",...], tokens: [...]} | Changed tokens ko yellow karo |
| audit:new | {correlation_id, events: [...]} | Audit timeline |

## Member 1 (Intelligence) - integration points
1. **Snapshot**: GET /api/snapshot  ya  `app.services.snapshot.build_snapshot(db)`.
   Frozen dataclasses: copy ke liye `dataclasses.replace(...)`. What-if simulator isi pe.
2. **ETA engine plug-in** (startup pe ek baar):

       from app.services.eta import set_eta_provider, EtaRange
       def my_eta(snapshot) -> dict[str, EtaRange]: ...
       set_eta_provider(my_eta)

   Phir har route/socket event tumhare ETA numbers use karega. Default algorithm
   `app/services/eta.py` me hai (reference).
3. **Approve action**: POST /api/tokens/{code}/reassign  {counter_code, reason?}.
   Eligibility check DB level pe bhi hota hai (422 if invalid).
4. **Audit chaining**: apne requests me `X-Correlation-ID: <id>` header bhejo; sab events
   us flow se jud jaate hain (GET /api/events?correlation_id=<id>).
5. Apne events (recommendation:created etc.) ke liye `from app.realtime import broadcast`;
   `await broadcast("recommendation:created", {...})`.
