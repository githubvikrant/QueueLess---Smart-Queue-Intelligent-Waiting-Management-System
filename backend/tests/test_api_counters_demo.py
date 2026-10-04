def test_reassign_blocks_ineligible(client):
    r = client.post("/api/tokens/Q106/reassign", json={"counter_code": "B"})  # consultation -> B
    assert r.status_code == 422
    assert r.json()["error"] == "not_eligible"
    assert "does not offer" in r.json()["message"]
    assert client.get("/api/tokens/Q106").json()["counter_code"] == "A"  # data nahi badla


def test_reassign_rules(client):
    assert client.post("/api/tokens/Q101/reassign", json={"counter_code": "B"}).status_code == 409  # in_service
    assert client.post("/api/tokens/Q104/reassign", json={"counter_code": "B"}).status_code == 409  # already B
    assert client.post("/api/tokens/Q103/reassign", json={"counter_code": "Z"}).status_code == 404
    r = client.post("/api/tokens/Q103/reassign", json={"counter_code": "B", "reason": "Agent: B is free"})
    assert r.json()["last_change_reason"] == "Agent: B is free"


def test_close_counter_moves_eligible_tokens(client):
    r = client.post("/api/counters/A/close")
    assert r.json()["is_open"] is False
    assert client.get("/api/tokens/Q103").json()["counter_code"] == "B"  # blood test -> B
    t106 = client.get("/api/tokens/Q106").json()  # consultation: koi counter nahi
    assert t106["counter_code"] is None
    assert t106["eta_text"] == "Waiting for a counter"
    ev = client.get("/api/events").json()
    assert any(e["type"] == "counter.closed" for e in ev)


def test_open_new_counter_c_places_unassigned(client):
    client.post("/api/counters/A/close")
    r = client.post("/api/counters", json={"code": "C", "name": "Counter C", "services": ["consultation"], "is_open": False})
    assert r.status_code == 201
    assert client.post("/api/counters", json={"code": "c", "name": "dup", "services": ["ecg"]}).status_code == 409
    client.post("/api/counters/C/open")
    assert client.get("/api/tokens/Q106").json()["counter_code"] == "C"


def test_join_when_no_counter_available(client):
    client.post("/api/counters/A/close")
    r = client.post("/api/tokens", json={"patient_name": "X", "service_code": "consultation"})
    assert r.status_code == 422 and r.json()["error"] == "no_counter_available"


def test_walk_ins(client):
    q = client.post("/api/demo/walk-ins", json={"count": 5}).json()
    assert q["stats"]["total"] == 17
    walkins = [t for t in q["tokens"] if t["is_walk_in"]]
    assert len(walkins) == 5
    for t in walkins:  # consultation kabhi B pe nahi
        if t["service_code"] == "consultation":
            assert t["counter_code"] == "A"


def test_inject_delay_validation(client):
    assert client.post("/api/demo/inject-delay", json={"counter_code": "A", "minutes": -5}).status_code == 422
    assert client.post("/api/demo/inject-delay", json={"counter_code": "Q", "minutes": 5}).status_code == 404


def test_delay_cleared_when_service_completes(client):
    client.post("/api/demo/inject-delay", json={"counter_code": "A", "minutes": 12})
    client.post("/api/tokens/Q101/complete")
    a = next(c for c in client.get("/api/counters").json() if c["code"] == "A")
    assert a["injected_delay_min"] == 0


def test_reset_restores_demo(client):
    client.post("/api/demo/walk-ins", json={"count": 5})
    client.post("/api/tokens/Q101/complete")
    q = client.post("/api/demo/reset").json()
    assert q["stats"]["total"] == 12 and q["stats"]["completed"] == 0
    assert client.get("/api/tokens/Q101").json()["status"] == "in_service"


def test_events_share_correlation_id(client):
    cid = "demo-flow-1"
    h = {"X-Correlation-ID": cid}
    client.post("/api/demo/inject-delay", json={"counter_code": "A", "minutes": 12}, headers=h)
    client.post("/api/tokens/Q103/reassign", json={"counter_code": "B"}, headers=h)
    ev = client.get("/api/events", params={"correlation_id": cid}).json()
    assert [e["type"] for e in ev] == ["counter.delay_injected", "token.reassigned"]
    assert ev[1]["token_code"] == "Q103" and ev[1]["payload"]["from"] == "A"


def test_eta_provider_plugin(client):
    from app.services.eta import EtaRange, set_eta_provider

    set_eta_provider(lambda snap: {t.code: EtaRange(5, 4, 6, 1) for t in snap.tokens if t.status == "waiting"})
    t = client.get("/api/tokens/Q103").json()
    assert (t["eta_min"], t["eta_max"]) == (4, 6)
    assert t["eta_text"] == "about 4-6 minutes"


def test_snapshot_what_if_does_not_touch_db(client):
    """Member 1 ka simulator pattern: snapshot copy -> scenario -> ETA, DB same."""
    import dataclasses

    from app.main import api
    from app.db.session import get_db
    from app.services.eta import default_eta_provider
    from app.services.snapshot import build_snapshot

    db = next(api.dependency_overrides[get_db]())
    snap = build_snapshot(db)
    moved = tuple(dataclasses.replace(t, counter_code="B") if t.code == "Q103" else t for t in snap.tokens)
    what_if = dataclasses.replace(snap, tokens=moved)
    assert default_eta_provider(what_if)["Q103"].eta_minutes < default_eta_provider(snap)["Q103"].eta_minutes
    assert client.get("/api/tokens/Q103").json()["counter_code"] == "A"
