"""
QR-based patient registration endpoint.

The manager generates a QR code that encodes a short registration token.
The patient scans it with the app's camera, then fills their details.
"""

import secrets
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Service

router = APIRouter(prefix="/api/qr", tags=["registration"])

# In-memory store for valid QR tokens (valid for 30 minutes)
# Format: { token: { "counter_code": str, "created_at": float } }
_valid_qr_tokens: dict[str, dict] = {}
QR_TOKEN_TTL = 60 * 30  # 30 minutes


def _cleanup():
    """Remove expired tokens."""
    now = time.time()
    expired = [k for k, v in _valid_qr_tokens.items() if now - v["created_at"] > QR_TOKEN_TTL]
    for k in expired:
        del _valid_qr_tokens[k]


@router.post("/generate")
def generate_qr(counter_code: str = "A", db: Session = Depends(get_db)):
    """
    Manager calls this to generate a new QR registration token.
    Returns a short token that encodes into a QR code.
    The frontend will encode this as a scannable QR.
    """
    _cleanup()
    token = secrets.token_urlsafe(8)  # short ~11 char token
    _valid_qr_tokens[token] = {
        "counter_code": counter_code.upper(),
        "created_at": time.time(),
    }
    # Return services too so the registration form can show options
    services = db.query(Service).order_by(Service.id).all()
    return {
        "qr_token": token,
        "counter_code": counter_code.upper(),
        "services": [{"code": s.code, "name": s.name} for s in services],
    }


@router.get("/validate/{token}")
def validate_qr(token: str, db: Session = Depends(get_db)):
    """
    Patient app calls this after scanning the QR to validate the token.
    Returns the counter code and available services.
    """
    _cleanup()
    info = _valid_qr_tokens.get(token)
    if not info:
        raise HTTPException(status_code=404, detail="QR code is invalid or has expired")
    services = db.query(Service).order_by(Service.id).all()
    return {
        "valid": True,
        "counter_code": info["counter_code"],
        "services": [{"code": s.code, "name": s.name} for s in services],
    }
