from contextlib import asynccontextmanager

import socketio
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_seeded(db)  # khali DB ho to demo data khud load
    yield


api = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="QueueLess queue engine (Member 3): tokens, counters, lifecycle, audit log, realtime.",
    lifespan=lifespan,
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.exception_handler(QueueError)
async def queue_error_handler(_req: Request, exc: QueueError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})


@api.exception_handler(StaleDataError)
async def stale_handler(_req: Request, _exc: StaleDataError):
    return JSONResponse(status_code=409, content={
        "error": "concurrent_update",
        "message": "This token was just changed by someone else. Refresh and try again.",
    })


@api.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "service": settings.app_name}


api.include_router(api_router)

# FastAPI aur Socket.IO ek hi server pe
app = socketio.ASGIApp(sio, other_asgi_app=api)
