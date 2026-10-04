"""
Database connection and session management for QueueLess.

This module provides the SQLAlchemy engine, session factory, and database
initialization functions used throughout the application.

PURPOSE: Establish SQLite database connection and provide session management
DEPENDENCIES: SQLAlchemy, core.config.Settings
SIDE EFFECTS: Creates database file if it doesn't exist, manages connection pool
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Create SQLAlchemy engine with SQLite database
# check_same_thread=False allows SQLite to be accessed from multiple threads
# which is needed for FastAPI's async nature
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
)

# Create a declarative base for ORM models
# All database models will inherit from this Base class
Base = declarative_base()

# Create session factory for database sessions
# SessionLocal will create new session instances when called
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    PURPOSE: Initialize database by creating all tables defined in models
    
    WORKFLOW:
        1. Call Base.metadata.create_all() to generate tables from ORM models
        2. Tables are created if they don't exist, existing tables are not modified
    
    DEPENDENCIES: Requires all model classes to be imported before calling
    SIDE EFFECTS: Creates tables in SQLite database file
    USAGE: Called at application startup in app/main.py
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """
    PURPOSE: Provide database session dependency for FastAPI routes
    
    PARAMETERS: None
    RETURNS: Generator yielding a SQLAlchemy Session instance
    
    WORKFLOW:
        1. Create new session from SessionLocal factory
        2. Yield session to the calling function (FastAPI route)
        3. After route completes, close session to release connection
    
    DEPENDENCIES: SessionLocal factory, engine
    SIDE EFFECTS: Manages database connection lifecycle
    USAGE: Used as FastAPI dependency: db: Session = Depends(get_db)
    
    EXAMPLE:
        @app.get("/api/queue/")
        def get_queue(db: Session = Depends(get_db)):
            return db.query(Token).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
