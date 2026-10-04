from sqlalchemy import inspect

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import make_engine


def test_all_tables_created():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert {"services", "counters", "counter_services", "tokens", "events"} <= names
