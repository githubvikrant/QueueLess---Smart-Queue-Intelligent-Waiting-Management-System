import asyncio

from app import realtime
from app.services import publisher


def test_publish_emits_queue_eta_audit(client, monkeypatch):
    sent = []

    async def fake_broadcast(event, payload):
        sent.append((event, payload))

    monkeypatch.setattr(publisher, "broadcast", fake_broadcast)
    publisher.reset_tracking()
    client.post("/api/tokens/Q105/no-show")  # pehla publish: baseline set hota hai
    sent.clear()
    client.post("/api/demo/inject-delay", json={"counter_code": "A", "minutes": 12})
    events = {e for e, _ in sent}
    assert {"queue:updated", "eta:updated", "audit:new"} <= events
    eta = next(p for e, p in sent if e == "eta:updated")
    assert {"Q103", "Q106", "Q109", "Q112"} <= set(eta["changed"])  # A ke tokens yellow
    assert "Q104" not in eta["changed"]  # B ke tokens nahi badle


def test_broadcast_without_clients_is_safe():
    asyncio.run(realtime.broadcast("queue:updated", {"x": 1}))
