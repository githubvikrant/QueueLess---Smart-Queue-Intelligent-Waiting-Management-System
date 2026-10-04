from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base


def make_engine(url: str) -> Engine:
    """SQLite engine with safe defaults: foreign keys ON, WAL mode (concurrent reads)."""
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool  # in-memory DB ek hi connection share kare (tests)

    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Saari tables banata hai (agar pehle se nahi hain)."""
    import app.models  # noqa: F401  (models register karne ke liye)

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: har request ko ek session, khatam hone pe close."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
