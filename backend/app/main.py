"""
FastAPI application entry point for QueueLess.

This module initializes the FastAPI application, configures CORS,
mounts Socket.IO, and includes all API routers.

PURPOSE: Main application entry point that bootstraps the entire backend
DEPENDENCIES: FastAPI, python-socketio, SQLAlchemy, core.config, core.events
SIDE EFFECTS: Initializes database, starts Socket.IO server, registers API routes
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from app.database.db import init_db, engine
from app.core.config import settings
from app.core.events import sio
from socketio import ASGIApp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    PURPOSE: Application lifespan manager for startup and shutdown events
    
    WORKFLOW:
        Startup:
            1. Initialize database tables (create if they don't exist)
            2. Print confirmation message
        Shutdown:
            1. Close database connections
            2. Clean up resources
    
    DEPENDENCIES: init_db() from database.db
    SIDE EFFECTS: Creates database tables on startup
    """
    # Startup: Initialize database
    print("Starting QueueLess backend...")
    init_db()
    print("Database initialized successfully")
    
    yield
    
    # Shutdown: Clean up resources
    print("Shutting down QueueLess backend...")
    engine.dispose()
    print("Database connections closed")


# Create FastAPI application instance
# title, description, and version for API documentation
app = FastAPI(
    title="QueueLess API",
    description="AI-powered adaptive queue management system for healthcare",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware to allow cross-origin requests
# For prototype, allow all origins (configure for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for prototype
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods
    allow_headers=["*"],  # Allows all headers
)

# Mount Socket.IO server with ASGI
# This enables real-time event broadcasting to frontend clients
socket_app = ASGIApp(sio, app)

# Include API routers
from app.api import queue, counters, notifications, agent, simulation
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(counters.router, prefix="/api/counters", tags=["counters"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"])


@app.get("/")
async def root():
    """
    PURPOSE: Root endpoint to verify API is running
    
    RETURNS: Welcome message with API information
    
    USAGE: Visit http://localhost:8000/ to check if backend is running
    """
    return {
        "message": "QueueLess API is running",
        "version": "1.0.0",
        "docs": "/docs",
        "socket_io": "/socket.io/"
    }


@app.get("/health")
async def health_check():
    """
    PURPOSE: Health check endpoint for monitoring
    
    RETURNS: Health status with configuration info
    
    USAGE: Call GET /health to verify backend is operational
    """
    return {
        "status": "healthy",
        "llm_model": settings.llm_model,
        "database_url": settings.database_url
    }


# Note: The actual app to run with uvicorn is 'socket_app', not 'app'
# Run command: uvicorn app.main:socket_app --reload --port 8000
