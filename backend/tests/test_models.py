import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.models import Counter, CounterService, Event, Service, Token, TokenStatus


def make_basics(db):
    blood = Service(code="blood_test", name="Blood Test", avg_duration_min=6)
    ecg = Service(code="ecg", name="ECG", avg_duration_min=8)
    consult = Service(code="consultation", name="General Consultation", avg_duration_min=10)
    a = Counter(code="A", name="Counter A")
    b = Counter(code="B", name="Counter B")
    db.add_all([blood, ecg, consult, a, b])
    db.flush()
    db.add_all(
        [
            CounterService(counter_id=a.id, service_id=blood.id),
            CounterService(counter_id=a.id, service_id=ecg.id),
            CounterService(counter_id=a.id, service_id=consult.id),
            CounterService(counter_id=b.id, service_id=blood.id),
            CounterService(counter_id=b.id, service_id=ecg.id),
        ]
    )
    db.commit()
    return blood, ecg, consult, a, b


def test_counter_eligibility_is_data(db):
    _, _, _, a, b = make_basics(db)
    assert b.service_codes == ["blood_test", "ecg"]  # B consultation nahi karta
    assert "consultation" in a.service_codes


def test_token_defaults(db):
    blood, *_ = make_basics(db)
    t = Token(code="Q101", patient_name="Ravi", service_id=blood.id)
    db.add(t)
    db.commit()
    assert t.status == TokenStatus.WAITING
    assert t.version == 1
    assert t.priority == 0
    assert t.counter_id is None
    assert t.created_at is not None


def test_token_code_unique(db):
    blood, *_ = make_basics(db)
    db.add(Token(code="Q101", patient_name="A", service_id=blood.id))
    db.commit()
    db.add(Token(code="Q101", patient_name="B", service_id=blood.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_enforced(db):
    db.add(Token(code="Q999", patient_name="X", service_id=12345))
    with pytest.raises(IntegrityError):
        db.commit()


def test_version_bumps_on_update(db):
    blood, *_ = make_basics(db)
    t = Token(code="Q101", patient_name="Ravi", service_id=blood.id)
    db.add(t)
    db.commit()
    t.status = TokenStatus.CALLED
    db.commit()
    assert t.version == 2


def test_stale_update_is_rejected(db):
    """Do jagah se ek saath update: doosra fail hona chahiye (double-click safety)."""
    from sqlalchemy.orm import sessionmaker

    blood, *_ = make_basics(db)
    t = Token(code="Q101", patient_name="Ravi", service_id=blood.id)
    db.add(t)
    db.commit()

    other = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    t2 = other.get(Token, t.id)
    t2.status = TokenStatus.CALLED
    other.commit()
    other.close()

    t.status = TokenStatus.NO_SHOW  # purani version pe
    with pytest.raises(StaleDataError):
        db.commit()


def test_event_log(db):
    ev = Event(correlation_id="c-1", type="delay.injected", payload={"minutes": 12})
    db.add(ev)
    db.commit()
    assert ev.payload["minutes"] == 12
    assert ev.created_at is not None
