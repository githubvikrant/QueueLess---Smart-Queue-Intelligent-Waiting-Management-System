def test_seed_has_12_tokens_2_counters_3_services(client):
    q = client.get("/api/queue").json()
    assert q["stats"]["total"] == 12
    assert q["stats"]["in_service"] == 2
    assert q["stats"]["waiting"] == 10
    assert {c["code"] for c in q["counters"]} == {"A", "B"}
    b = next(c for c in q["counters"] if c["code"] == "B")
    assert sorted(b["service_codes"]) == ["blood_test", "ecg"]


def test_trailing_slash_works(client):
    assert client.get("/api/queue/").status_code == 200


def test_patient_view(client):
    t = client.get("/api/tokens/Q103").json()
    assert t["counter_code"] == "A"
    assert t["status"] == "waiting"
    assert t["eta_text"].startswith("about ")
    assert client.get("/api/tokens/q103").status_code == 200  # case-insensitive


def test_unknown_token_404(client):
    r = client.get("/api/tokens/Q999")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_snapshot_is_json_and_complete(client):
    s = client.get("/api/snapshot").json()
    assert len(s["tokens"]) == 12 and len(s["counters"]) == 2 and len(s["services"]) == 3
    assert "now" in s


def test_eta_story_numbers(client):
    """Demo story: Counter A pe +12 min delay -> Q103 ~22 min; B pe shift -> ~8 min."""
    base = client.get("/api/tokens/Q103").json()
    assert 9 < base["eta_minutes"] < 11  # Q101 ki consultation 10 min
    client.post("/api/demo/inject-delay", json={"counter_code": "A", "minutes": 12})
    delayed = client.get("/api/tokens/Q103").json()
    assert 21 < delayed["eta_minutes"] < 23
    assert "behind" in delayed["last_change_reason"]
    r = client.post("/api/tokens/Q103/reassign", json={"counter_code": "B"})
    assert r.status_code == 200
    moved = r.json()
    assert moved["counter_code"] == "B"
    assert 7 < moved["eta_minutes"] < 9
    assert moved["position"] == 1


def test_eta_range_contains_estimate(client):
    for t in client.get("/api/queue").json()["tokens"]:
        if t["eta_minutes"] is not None and t["status"] == "waiting":
            assert t["eta_min"] <= t["eta_minutes"] <= t["eta_max"]
