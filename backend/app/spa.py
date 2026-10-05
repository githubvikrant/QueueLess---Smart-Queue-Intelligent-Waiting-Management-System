"""Production me built frontend (frontend/dist) ko FastAPI se hi serve karta hai.
Isse ek hi service/URL pe sab chalta hai: /api, /socket.io aur dashboard.
Local dev me dist nahi hota, to ye kuch nahi karta (Vite apna kaam karta hai)."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def mount_frontend(api: FastAPI) -> None:
    index = DIST / "index.html"
    if not index.is_file():
        return

    @api.get("/{path:path}", include_in_schema=False)
    def serve_frontend(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)  # React Router ke routes (refresh pe bhi chale)