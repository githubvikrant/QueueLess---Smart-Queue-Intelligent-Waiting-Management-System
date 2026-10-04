import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core import clock
from app.db.base import Base
from app.db.session import get_db, make_engine
from app.main import api
from app.seeding.seeder import reseed
from app.services import publisher
from app.services.eta import reset_eta_provider


@pytest.fixture()
def db():
    """Fresh khali in-memory database."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client():
    """API client jisme CityCare demo data seeded hai."""
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        reseed(s)
    clock.reset()
    publisher.reset_tracking()
    reset_eta_provider()

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    api.dependency_overrides[get_db] = override
    yield TestClient(api)
    api.dependency_overrides.clear()
    engine.dispose()
