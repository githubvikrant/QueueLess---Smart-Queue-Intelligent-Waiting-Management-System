"""
FastAPI application entry point for QueueLess.

This module initializes the FastAPI application, configures CORS,
mounts Socket.IO, and includes all API routers.

PURPOSE: Main application entry point that bootstraps the entire backend
DEPENDENCIES: FastAPI, python-socketio, SQLAlchemy, core.config, core.events
SIDE EFFECTS: Initializes database, starts Socket.IO server, registers API routes
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import QueueError
from app.db.session import SessionLocal, init_db
from app.realtime import sio
from app.seeding.seeder import ensure_seeded
import socketio


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    PURPOSE: Application lifespan manager for startup and shutdown events
    
    WORKFLOW:
        Startup:
            1. Initialize database tables (create if they don't exist)
            2. Seed demo data if database is empty
        Shutdown:
            1. Close database connections
            2. Clean up resources
    
    DEPENDENCIES: init_db() from db.session, ensure_seeded() from seeding.seeder
    SIDE EFFECTS: Creates database tables on startup
    """
    # Startup: Initialize database
    print("Starting QueueLess backend...")
    init_db()
    
    # Seed demo data if database is empty
    with SessionLocal() as db:
        ensure_seeded(db)
    
    print("Database initialized and seeded successfully")
    
    yield
    
    # Shutdown: Clean up resources
    print("Shutting down QueueLess backend...")


# Create FastAPI application instance
api = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="QueueLess queue engine (Member 3) + AI Agent (Member 1): tokens, counters, lifecycle, audit log, realtime, LLM recommendations.",
    lifespan=lifespan,
)

# Add CORS middleware
api.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@api.exception_handler(QueueError)
async def queue_error_handler(_req: Request, exc: QueueError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})


@api.exception_handler(StaleDataError)
async def stale_handler(_req: Request, _exc: StaleDataError):
    return JSONResponse(status_code=409, content={
        "error": "concurrent_update",
        "message": "This token was just changed by someone else. Refresh and try again.",
    })


# Health check endpoint
@api.get("/api/health", tags=["system"])
def health():
    return {
        "status": "ok", 
        "service": settings.app_name,
        "llm_model": settings.llm_model if hasattr(settings, 'llm_model') else "not configured"
    }


# Include Member 3's API router
api.include_router(api_router)

# FastAPI aur Socket.IO ek hi server pe
app = socketio.ASGIApp(sio, other_asgi_app=api)
