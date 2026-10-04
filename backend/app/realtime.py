import socketio
from app.core.config import settings

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins,
)


@sio.event
async def connect(sid, environ):
    await sio.emit("system:connected", {"sid": sid}, to=sid)


async def broadcast(event: str, payload: dict) -> None:
    """Backend ka koi bhi module realtime event isi function se bhejega."""
    await sio.emit(event, payload)
