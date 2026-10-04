from fastapi import APIRouter

from app.api.routes import counters, demo, queue, tokens

api_router = APIRouter()
for r in (queue.router, tokens.router, counters.router, demo.router):
    api_router.include_router(r)
