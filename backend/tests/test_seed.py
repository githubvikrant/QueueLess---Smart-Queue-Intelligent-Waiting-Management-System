from sqlalchemy import func, select

from app.models import Counter, Service, Token
from app.seeding.seeder import ensure_seeded, reseed


def test_reseed_is_idempotent(db):
    reseed(db)
    reseed(db)
    assert db.scalar(select(func.count()).select_from(Token)) == 12
    assert db.scalar(select(func.count()).select_from(Counter)) == 2
    assert db.scalar(select(func.count()).select_from(Service)) == 3


def test_ensure_seeded_only_when_empty(db):
    ensure_seeded(db)
    t = db.scalar(select(Token).where(Token.code == "Q101"))
    t.patient_name = "Changed"
    db.commit()
    ensure_seeded(db)
    assert db.scalar(select(Token.patient_name).where(Token.code == "Q101")) == "Changed"
