def post(client, path, **kw):
    return client.post(path, **kw)


def test_join_assigns_eligible_counter(client):
    r = post(client, "/api/tokens", json={"patient_name": "Test Patient", "service_code": "consultation"})
    assert r.status_code == 201
    t = r.json()
    assert t["code"] == "Q113"
    assert t["counter_code"] == "A"  # B consultation nahi karta
    assert t["status"] == "waiting"


def test_join_validation(client):
    assert post(client, "/api/tokens", json={"patient_name": "", "service_code": "ecg"}).status_code == 422
    assert post(client, "/api/tokens", json={"patient_name": "X", "service_code": "nope"}).status_code == 404


def test_full_lifecycle_with_clock(client):
    assert post(client, "/api/tokens/Q103/call").status_code == 409  # Q101 abhi A pe busy hai
    post(client, "/api/tokens/Q101/complete")
    assert post(client, "/api/tokens/Q103/call").json()["status"] == "called"
    assert post(client, "/api/tokens/Q103/start").json()["status"] == "in_service"
    post(client, "/api/demo/advance-clock", json={"minutes": 7})
    done = post(client, "/api/tokens/Q103/complete").json()
    assert done["status"] == "completed"
    q = client.get("/api/queue").json()
    assert q["stats"]["completed"] == 2


def test_actual_duration_recorded(client, ):
    post(client, "/api/demo/advance-clock", json={"minutes": 9})
    post(client, "/api/tokens/Q101/complete")
    ev = client.get("/api/events", params={"limit": 10}).json()
    done = [e for e in ev if e["type"] == "token.completed"][-1]
    assert 8.9 < done["payload"]["actual_duration_min"] < 9.2


def test_invalid_transitions_409(client):
    assert post(client, "/api/tokens/Q104/start").status_code == 409  # waiting -> in_service
    assert post(client, "/api/tokens/Q104/complete").status_code == 409
    post(client, "/api/tokens/Q101/complete")
    again = post(client, "/api/tokens/Q101/complete")
    assert again.status_code == 409 and again.json()["error"] == "invalid_transition"


def test_counter_busy(client):
    r = post(client, "/api/tokens/Q104/call")  # B pe Q102 in_service
    assert r.status_code == 409 and r.json()["error"] == "counter_unavailable"


def test_call_next_respects_priority(client):
    post(client, "/api/tokens/Q101/complete")
    vip = post(client, "/api/tokens", json={"patient_name": "Emergency", "service_code": "consultation", "priority": 3}).json()
    assert vip["position"] == 1  # A ki line me sabse aage
    called = post(client, "/api/counters/A/call-next").json()
    assert called["code"] == vip["code"]


def test_no_show_skip_recall(client):
    assert post(client, "/api/tokens/Q105/no-show").json()["status"] == "no_show"
    assert post(client, "/api/tokens/Q105/recall").json()["status"] == "waiting"
    assert post(client, "/api/tokens/Q105/skip").json()["status"] == "skipped"
    assert post(client, "/api/tokens/Q105/recall").json()["status"] == "waiting"
    assert post(client, "/api/tokens/Q105/start").status_code == 409


def test_no_show_removes_from_eta(client):
    before = client.get("/api/tokens/Q107").json()["eta_minutes"]
    post(client, "/api/tokens/Q105/no-show")  # Q105 B pe Q107 se pehle tha
    after = client.get("/api/tokens/Q107").json()["eta_minutes"]
    assert after < before
    assert client.get("/api/tokens/Q105").json()["eta_minutes"] is None
